# Plan: Plan-Execute-Replan Execution Model

> Status: Pending
> Created: 2026-03-06

## Problem Statement

The current execution pipeline is one-shot: the LLM generates a complete plan once, `PlanExecutor` executes steps sequentially, and any failure (step execution or verification) immediately transitions the task to `NEEDS_HUMAN`. The agent cannot recover from execution errors autonomously.

This causes three categories of preventable failures:

1. **LLM guesses wrong file content** — the planner works from stale or incomplete repo context. A step fails because the file doesn't match expectations. A second attempt with the actual file content would succeed.
2. **Inter-step dependency errors** — step N produces output that step N+1 doesn't anticipate. With the actual output visible, the LLM can adjust.
3. **Test/lint failures after execution** — all steps succeed, but verification fails. The LLM could fix the code if given the verification output.

Goal: introduce a bounded re-plan loop so the agent can feed execution history back to the LLM for a corrective plan, up to N rounds.

## Design

```
Task ──> PLAN (LLM) ──> EXECUTE (steps) ──> VERIFY (checks)
              ^              │                    │
              │         fail │               fail │
              │              v                    v
              │         ROUND CHECK: round < max?
              │              │ yes           │ no
              └── REPLAN ◄───┘               v
                                        NEEDS_HUMAN
```

### Core Principles

- **Bounded**: `max_replan_rounds` (default 3, configurable via directive)
- **Incremental**: re-plan starts from the point of failure, not from scratch
- **Observable**: each re-plan round emits structured events
- **Safe**: every re-plan passes constitution check + SafetyPolicy
- **Token-controlled**: per-task token cap prevents runaway consumption

### Re-plan Trigger Conditions

| Trigger | Current Behavior | New Behavior |
|---------|-----------------|--------------|
| Step execution failure | NEEDS_HUMAN | Re-plan (with execution history) |
| Verification failure (test/lint) | NEEDS_HUMAN | Re-plan (with verification output) |
| Constitution block | NEEDS_HUMAN | Unchanged (requires human strategy change) |
| Safety block | NEEDS_HUMAN | Unchanged |

## Component Changes

### 1. Models (`core/models.py`)

**New dataclass: `ExecutionRound`**

```python
@dataclass
class ExecutionRound:
    round_number: int
    plan_steps: List[Dict[str, str]]   # serialized PlanStep list
    results: List[Dict[str, str]]      # serialized ExecutionResult list
    verification: str                   # verification output (empty if execution failed before verify)
    trigger: str                        # "step_failure" | "verification_failure"
    token_cost: int = 0
```

**Task — new field:**

- `replan_history: str = ""` — JSON-serialized list of `ExecutionRound` summaries. Appended after each round.

**Directive — new fields:**

- `max_replan_rounds: int = 3` — maximum re-plan attempts per task. Set to 1 for current one-shot behavior.
- `max_tokens_per_task: int = 0` — per-task token cap (0 = unlimited, rely on global budget only).

**No changes to `TaskStatus`** — re-planning is an internal detail of the `EXECUTING` phase.

### 2. Prompt (`llm/prompts/replan_task.txt`)

New template. Structure:

```
{constitution_section}

You are the re-planning module of an autonomous engineering agent.
A previous plan for this task was executed but failed. Your job is to produce
a corrective plan that fixes the failure without repeating successful steps.

## Task
Title: {task_title}
Description: {task_description}
Source: {task_source}

## Previous Execution (Round {round_number})
### Steps executed
{executed_steps}

### Failure trigger
{trigger}

### Verification output (if applicable)
{verification_output}

## Re-planning Principles
- Do NOT repeat steps that already succeeded — their effects are already in the worktree.
- Focus on the minimal correction needed to address the failure.
- If the failure reveals a misunderstanding of the codebase, adjust the approach.
- If a file was written incorrectly, use edit_file with the corrected content.
- Include a verification step so the agent can confirm the fix.
- You have {remaining_rounds} re-plan attempt(s) remaining.

{directive_section}

## Output Format (strict JSON)
<same as plan_task.txt>
```

Output format is identical to `plan_task.txt` so existing parsing logic in `_call_and_parse_plan()` is reused.

### 3. Planner (`execution/planner.py`)

**New function: `replan_task_with_constitution()`**

```python
def replan_task_with_constitution(
    task: Task,
    workspace: Path,
    directive: Directive,
    constitution: Constitution,
    llm: LLMClient,
    executed_steps: str,          # formatted execution log
    verification_output: str,     # formatted verification result (may be empty)
    trigger: str,                 # "step_failure" | "verification_failure"
    round_number: int,
    remaining_rounds: int,
) -> TaskPlan:
```

- Renders `replan_task.txt` with the execution context
- Calls `_call_and_parse_plan()` (existing shared logic)
- Returns a `TaskPlan` that contains only the corrective steps

**New helper: `format_execution_history_for_replan()`**

Formats the list of `ExecutionResult` objects into a compact string for the LLM prompt. Includes step action, target, success/failure status, and output (truncated). For steps with `edit_file`/`create_file` actions that succeeded, omits the full content to save tokens but notes the file was written.

### 4. Observer (`observability/observer.py`)

Three new convenience emitters on `Observer`:

```python
def replan_triggered(self, task_id: str, round_number: int, trigger: str) -> None:
    """Emitted when a re-plan round begins."""
    self.emit(AgentEvent(
        phase="plan", action="replan_triggered", task_id=task_id,
        detail=f"round={round_number} trigger={trigger}",
    ))

def replan_created(self, task_id: str, round_number: int, step_count: int) -> None:
    """Emitted when the LLM returns a corrective plan."""
    self.emit(AgentEvent(
        phase="plan", action="replan_created", task_id=task_id,
        detail=f"round={round_number} steps={step_count}",
        success=True,
    ))

def replan_exhausted(self, task_id: str, total_rounds: int) -> None:
    """Emitted when max re-plan rounds are exceeded."""
    self.emit(AgentEvent(
        phase="plan", action="replan_exhausted", task_id=task_id,
        detail=f"exhausted after {total_rounds} rounds",
        success=False,
    ))
```

### 5. Agent (`agent.py`)

**Extract `_plan_execute_verify_loop()` from `_execute_single_task()`.**

The new method encapsulates the plan → execute → verify cycle with re-plan support:

```python
def _plan_execute_verify_loop(
    self,
    task: Task,
    directive: Directive,
    constitution: Constitution,
    execution_workspace: Path,
    experience_context: str,
    worktree_path: Path | None,
    branch_name: str,
) -> tuple[bool, TaskPlan, list[ExecutionResult]]:
    """Run the plan-execute-verify loop with bounded re-planning.

    Returns (success, final_plan, final_results).
    """
```

**Loop logic:**

```
round = 0
max_rounds = directive.max_replan_rounds  # default 3

while round < max_rounds:
    if round == 0:
        plan = plan_task_with_constitution(...)
    else:
        plan = replan_task_with_constitution(..., executed_steps, verification_output, trigger, round, max_rounds - round)

    # Constitution check (every round)
    for step in plan.steps:
        allowed, reason = constitution.check_action_allowed(step.action, step.target)
        if not allowed:
            → NEEDS_HUMAN (constitution block, no retry)

    # Execute
    all_ok, results = executor.execute_plan(plan)

    if not all_ok:
        if round + 1 < max_rounds and not token_budget_exceeded:
            trigger = "step_failure"
            obs.replan_triggered(task.id, round + 1, trigger)
            round += 1
            continue
        else:
            → NEEDS_HUMAN (exhausted)

    # Verify
    verification = verify_task(...)

    if not verification.passed:
        if round + 1 < max_rounds and not token_budget_exceeded:
            trigger = "verification_failure"
            obs.replan_triggered(task.id, round + 1, trigger)
            round += 1
            continue
        else:
            → NEEDS_HUMAN (exhausted)

    return (True, plan, results)  # success
```

**Key behaviors:**

- Worktree is created once, outside the loop. All rounds share the same worktree. Subsequent rounds operate on the cumulative filesystem state.
- Each round's execution history is appended to `task.replan_history`.
- Per-task token check runs before each re-plan: `cumulative_tokens > directive.max_tokens_per_task` → stop.
- Experience extraction runs once after the loop completes (on final success or failure).
- `_execute_single_task()` is simplified: it handles human-resolved tasks, experience retrieval, worktree setup, calls `_plan_execute_verify_loop()`, then does git workflow and finalization.

### 6. Storage (`storage/store.py`)

SQLite migration — add column:

```sql
ALTER TABLE tasks ADD COLUMN replan_history TEXT DEFAULT '';
```

Applied via the existing migration pattern (check column existence, alter if missing).

### 7. Executor (`execution/executor.py`)

**No changes to `PlanExecutor`.**

New standalone helper function:

```python
def format_execution_history_for_replan(results: list[ExecutionResult]) -> str:
    """Format execution results for inclusion in a re-plan prompt.

    Differs from format_execution_log() by:
    - Including step content summary for context
    - Truncating successful output more aggressively
    - Emphasizing failure details
    """
```

This could alternatively live in `planner.py`. Placing it in `executor.py` keeps it close to `ExecutionResult`.

## Token Budget Management

Three layers of protection:

1. **Global budget** — existing `BudgetExhaustedError` in `LLMClient.generate()`. Unchanged.
2. **Per-task cap** — `directive.max_tokens_per_task`. Checked before each re-plan round. If cumulative task tokens exceed the cap, the loop exits and task goes to NEEDS_HUMAN.
3. **Round limit** — `directive.max_replan_rounds`. Hard upper bound on re-plan attempts.

## Safety Invariants

All existing safety mechanisms remain unchanged:

- Constitution check runs on every plan (including re-plans)
- SafetyPolicy runs on every step execution
- Worktree isolation unchanged (one worktree per task)
- IMMUTABLE_PATHS unchanged
- Force push / direct push to main still blocked

## Backward Compatibility

- All new fields have defaults (`replan_history=""`, `max_replan_rounds=3`, `max_tokens_per_task=0`)
- `max_replan_rounds=1` is functionally equivalent to current one-shot behavior (no re-plan on failure)
- TaskStatus enum unchanged — EXECUTING covers the re-plan loop
- Existing prompt template `plan_task.txt` unchanged
- Dashboard API naturally compatible — `replan_history` is a new optional field on Task

## What NOT to Change

- `PlanExecutor` internal logic
- `SafetyPolicy` / `Constitution`
- `TaskStatus` enum
- `GitWorkflow` (one worktree per task)
- `verify_task()`
- Discovery pipeline
- Experience extraction (runs once after loop completes)

## Implementation Sequence

1. **Models** — `ExecutionRound` dataclass, `Task.replan_history`, `Directive.max_replan_rounds` + `Directive.max_tokens_per_task`, SQLite migration
2. **Prompt** — create `replan_task.txt`
3. **Planner** — `replan_task_with_constitution()` + `format_execution_history_for_replan()`
4. **Observer** — 3 new convenience emitters
5. **Agent** — extract `_plan_execute_verify_loop()`, refactor `_execute_single_task()`
6. **Tests** — unit tests for each component (test_v2_replan_*.py or additions to existing test files)
7. **Design doc** — update `docs/design/execution.md` with Plan-Execute-Replan section

## Open Questions

1. **Re-plan context size** — For plans with 10+ steps, the execution history may consume significant context tokens. Start with full history; add truncation/summarization later if needed.
2. **Verification granularity** — Currently verification runs all checks. Could optimize to only re-run failed checks. Defer to avoid scope creep.
3. **Semantic drift detection** — Steps may "succeed" but produce unexpected output. Complex to detect reliably. Defer.
4. **Learning from re-plan patterns** — Analyzing which task types frequently need re-planning. Data accumulates naturally in `replan_history`; analysis can be added later.

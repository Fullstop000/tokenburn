# Execution Module Design

> Module: `src/llm247_v2/execution/`
> Last updated: 2026-03-09

## Purpose

The execution module takes a queued task and carries it through planning, safe execution, verification, and git shipping. It is the part of the agent that actually changes the codebase.

## Pipeline

```
queued task
    │
    ▼
git_ops.py          — create isolated git worktree on a fresh branch
    │
    ▼
┌───────────────────── Plan-Execute-Verify Loop (max N rounds) ──┐
│                                                                 │
│  planner.py          — LLM generates a plan (or re-plan)       │
│      │                                                          │
│      ▼                                                          │
│  constitution check  — every step checked against safety rules  │
│      │ (blocked → NEEDS_HUMAN, no retry)                        │
│      ▼                                                          │
│  executor.py         — execute plan steps sequentially          │
│      │ (step fails → re-plan if rounds remain)                  │
│      ▼                                                          │
│  verifier.py         — post-execution checks                    │
│      │ (fails → re-plan if rounds remain)                       │
│                                                                 │
└─────────────────── exhausted → NEEDS_HUMAN ────────────────────┘
    │ (success)
    ▼
git_ops.py          — stage + commit + push + create PR
    │
    ▼
COMPLETED
```

## Components

### Planner (`planner.py`)

Calls the LLM with a structured prompt (`plan_task.txt`) that includes:
- Task title and description
- Repository context (relevant files read from disk)
- Constitution constraints
- Directive rules (forbidden paths, max file changes)
- Relevant past experiences (injected by `agent.py` before calling planner)

Output is a `TaskPlan`: an ordered list of `PlanStep` objects, each with `action`, `target`, `content`, and `description`.

Supported actions: `edit_file`, `create_file`, `run_command`, `delete_lines`.

### Executor (`executor.py`)

Executes each `PlanStep` sequentially. Each step result is logged (success/failure + output). If any step fails, execution stops and the task moves to `NEEDS_HUMAN`.

`SafetyPolicy` (`safety.py`) is consulted before each `run_command` step — commands not on the allowlist are rejected.

### Verifier (`verifier.py`)

Runs post-execution checks on changed files:
- **Syntax check** — Python `compile()` on edited `.py` files
- **Test runner** — `pytest` if tests exist
- **Secret scan** — basic regex scan for accidentally committed secrets

All checks must pass for the task to proceed to git shipping.

### Repository PR CI

The repository also runs one first-party GitHub Actions workflow for pull requests and pushes to `main`.
That workflow reuses the maintained verification commands:
- backend: `coverage run -m unittest discover -s tests -p "test_v2_*.py" -v`
- frontend: `npm run build` from `frontend/`

The CI workflow is a repository-level gate for human review, not a replacement for task-local verification inside the agent loop.

### Git Operations (`git_ops.py`)

**Worktree isolation** is the core safety mechanism for self-modification:

```
Main workspace (agent running here, never modified directly)
      │
      └── git worktree add .worktrees/<task-id> -b agent/<task-id>-<name>
               │
               └── All file edits happen here
                    │
                    ├── git commit + push
                    ├── gh pr create
                    └── git worktree remove (cleanup)
```

The main workspace is never touched during execution. If worktree creation fails (e.g., not a git repo), the agent falls back to in-place execution with standard branch isolation.

### Safety Policy (`safety.py`)

Two enforcement layers:

1. **Path protection** — forbidden paths from the directive (e.g., `.env`, `.git`) are blocked at the `edit_file` / `create_file` / `delete_lines` level.
2. **Command allowlist** — `run_command` steps are checked against a list of safe commands (e.g., `pytest`, `rg`, `python`, `pip`). Commands not on the list are rejected and the task moves to `NEEDS_HUMAN`.

### Constitution (`core/constitution.py`)

Immutable rules encoded in `constitution.md` and enforced by `constitution.py`. The agent checks every plan step against the constitution before execution begins. If a step is blocked:
- Task moves to `NEEDS_HUMAN`
- A structured help request explains which step was blocked and why
- Human can edit the constitution or the task scope, then click Resolve

**The agent MUST NOT modify `constitution.md` or `safety.py`.** These paths are in `IMMUTABLE_PATHS`.

## NEEDS_HUMAN Flow

When a task is blocked at any stage:

```
NEEDS_HUMAN status set
    │
    ├── human_help_request field populated (structured: phase, what happened, suggested actions)
    ├── experience extracted ("failed" outcome)
    └── dashboard shows request in Help Center tab
              │
              ▼ human inspects + fixes + clicks Resolve
              │
              ▼
    HUMAN_RESOLVED status set
              │
              ▼
    agent re-runs verification (skips planning/execution)
```

## Design Constraints

- **All code changes go through PRs** — `SafetyPolicy` blocks direct push to main/master. Force push is also blocked.
- **Worktree cleanup is always attempted** — even if execution fails mid-way, the worktree is removed to prevent accumulation.
- **Max file changes per task** — enforced by directive `max_file_changes_per_task`. Plans with more steps are truncated.
- **LLM fallback plan** — if planning fails (LLM error, parse error), a zero-step `TaskPlan` is returned. The task does not crash; it simply does nothing and logs a warning.

## Plan-Execute-Replan

> Origin: [`docs/plans/2026-03-06-plan-execute-replan.md`](../plans/2026-03-06-plan-execute-replan.md)

### Problem

The current pipeline is one-shot: plan once, execute, verify. Any failure at execution or verification immediately moves the task to `NEEDS_HUMAN`. The agent cannot recover from errors that the LLM could fix if given the failure context — wrong file content, inter-step dependency issues, or test failures.

### Design

A bounded re-plan loop wraps the existing plan → execute → verify sequence:

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

**Key properties:**

- **Bounded** — `directive.max_replan_rounds` (default 3) caps retry attempts. Set to 1 for one-shot behavior.
- **Incremental** — re-plan receives the execution history and operates on cumulative worktree state. It generates only corrective steps, not a full re-do.
- **Observable** — three structured events: `replan_triggered`, `replan_created`, `replan_exhausted`.
- **Safe** — every re-plan passes constitution check. Every step passes SafetyPolicy. No safety invariants are relaxed.
- **Token-controlled** — three layers: global budget (`BudgetExhaustedError`), per-task cap (`directive.max_tokens_per_task`), round limit.

### Re-plan Triggers

| Trigger | Behavior |
|---------|----------|
| Step execution failure | Re-plan with execution history |
| Verification failure | Re-plan with verification output |
| Constitution block | NEEDS_HUMAN (no retry — requires human strategy change) |
| Safety block | NEEDS_HUMAN (no retry) |
| Round limit exceeded | NEEDS_HUMAN (with full `replan_history`) |
| Per-task token cap exceeded | NEEDS_HUMAN |

### Components Affected

- **`core/models.py`** — `ExecutionRound` dataclass, `Task.replan_history` field, `Directive.max_replan_rounds` + `Directive.max_tokens_per_task`
- **`llm/prompts/replan_task.txt`** — re-plan prompt template (same output format as `plan_task.txt`)
- **`execution/planner.py`** — `replan_task_with_constitution()`, `format_execution_history_for_replan()`
- **`observability/observer.py`** — three new convenience emitters
- **`agent.py`** — `_plan_execute_verify_loop()` extracted from `_execute_single_task()`
- **`storage/store.py`** — migration: `ALTER TABLE tasks ADD COLUMN replan_history TEXT DEFAULT ''`

### What Does NOT Change

- `PlanExecutor` internal logic (remains a pure step executor)
- `SafetyPolicy` / `Constitution` enforcement
- `TaskStatus` enum (re-planning is internal to `EXECUTING`)
- `GitWorkflow` (one worktree per task, created before loop, shared across rounds)
- `verify_task()` logic
- Discovery pipeline
- Experience extraction (runs once after loop exits)

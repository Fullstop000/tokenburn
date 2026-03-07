# Plan: ReAct Tool-Calling Execution Loop

> Status: Completed
> Created: 2026-03-07
> Completed: 2026-03-07
> PR: https://github.com/Fullstop000/sprout/pull/12
> Proposal: [docs/proposals/2026-03-07-react-tool-calling.md](../proposals/2026-03-07-react-tool-calling.md)

## Goal

Replace the Plan-then-Execute + replan model with a ReAct tool-calling loop in which the agent autonomously decides every aspect of task execution — including whether to use git isolation, when to commit, and when to create a PR. `agent.py` becomes a thin orchestrator that picks tasks and starts the loop; the loop itself is the agent.

## Philosophy

The previous design treated `agent.py` as the decision-maker and `ReActLoop` as an executor. This plan inverts that:

- **`ReActLoop` is the agent.** It decides what to do, in what order, with what tools.
- **`agent.py` is the scheduler.** It picks a task, builds context, starts the loop, and records the result.
- **Git operations are tools.** `create_worktree`, `commit`, `push`, `create_pr` are tools the agent calls when it judges they are needed — based on constitution rules, experience, or task reasoning. They are not infrastructure imposed by the orchestrator.
- **Workspace is abstract.** The loop receives a root `workspace: Path`. What that path is — main repo, a worktree, `/tmp`, the entire filesystem — is not the loop's concern.

## Scope

**In scope:** `execution/tools/` (new), `execution/loop.py` (new), `core/models.py`, `agent.py`, `llm/client.py`, `llm/prompts/`

**Out of scope:** `discovery/`, `storage/`, `observability/`, `dashboard/`

## Architecture After

```
agent.py (scheduler)
  task = store.get_next_executable_task()
  context = build_context(task, workspace, directive, constitution, experience)
  success, trace = ReActLoop(llm, tools, observer).run(task, context)
  store.record(task, trace)
  extract_learnings(task, trace)
```

```
ReActLoop (the agent)
  loop until finish() or max_steps or budget:
    llm.generate_with_tools(messages, tool_schemas)
    → structured tool_call (no JSON parsing)
    safety + constitution check
    tool_handler.execute()
    append (tool_call, tool_result) to messages + trace
    observer.execute_step(...)
```

The agent decides the full workflow. A typical self-modification task might look like:

```
read_file(src/llm247_v2/agent.py)          ← understand current state
search_files("replan", "src/")             ← gather context
git_create_worktree("fix-replan-logic")    ← decide isolation is needed
edit_file(src/llm247_v2/agent.py, ...)     ← make the change
run_command(python -m pytest tests/)       ← self-verify
git_commit("fix: ...")                     ← commit in the worktree
git_push()
git_create_pr("Fix replan logic", "...")
finish("Completed: fixed replan logic")
```

A read-only analysis task:

```
search_files("TODO", "src/")
read_file(src/llm247_v2/execution/executor.py)
finish("Analysis complete: found 3 tech debt items, added to store")
```

No worktree, no commit, no PR — because the agent decided none were needed.

## Tool Set

| Category | Tool | Arguments | Purpose |
|----------|------|-----------|---------|
| **filesystem** | `read_file` | `path` | Read file content |
| | `list_directory` | `path` | List directory entries |
| | `search_files` | `pattern`, `path` | Grep across files |
| | `write_file` | `path`, `content`, `overwrite=false` | Full write — create new file or overwrite existing; `overwrite` must be true to replace an existing file |
| | `edit_file` | `path`, `old_string`, `new_string` | Search-and-replace within a file; fails if `old_string` not found or not unique |
| | `delete_file` | `path` | Delete a file |
| **shell** | `run_command` | `command` | Execute a shell command |
| **git** | `git_create_worktree` | `branch_name` | Create an isolated git worktree; subsequent file tools operate inside it |
| | `git_commit` | `message` | Stage all changes and commit in the current worktree |
| | `git_push` | — | Push the current branch to remote |
| | `git_create_pr` | `title`, `body` | Open a pull request |
| **control** | `finish` | `summary` | Signal task completion |

**`write_file` vs `edit_file`:**
- `write_file` requires the agent to supply the entire file content. Use for new files or complete rewrites.
- `edit_file` requires only the target string and its replacement. Use for targeted changes to existing files — token-efficient and safe (no risk of accidentally dropping surrounding content).

Safety rules apply per tool call, before execution. A blocked call returns an error message the agent can reason about.

`git_create_worktree` stores the resulting path in `LoopState.active_workspace` so subsequent file tools automatically operate inside the worktree. If the agent never calls `git_create_worktree`, file tools operate on the root workspace.

**Future extensions (not in this plan):**
- `apply_patch` — apply a unified diff; useful for large multi-file refactors
- `run_background` — start a long-running process (e.g. dev server) and manage its lifecycle
- `sessions_spawn` — spawn a sub-agent for a subtask (multi-agent evolution)

## Component Changes

### 1. `llm/client.py` — extend `LLMClient` protocol

```python
class LLMClient(Protocol):
    def generate(self, prompt: str) -> str: ...                 # existing, unchanged
    def generate_with_tools(                                    # new
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> tuple[str | None, list[ToolCall]]: ...
    # Returns (text_content, tool_calls). Exactly one will be populated.
```

`ArkAdapter` implements `generate_with_tools` by:
1. POSTing to the chat completions endpoint with the `tools` field
2. Reading `response["choices"][0]["message"]["tool_calls"]` as structured objects
3. Constructing `ToolCall` instances directly — no string parsing

`generate` remains unchanged. All existing callers are unaffected.

---

### 2. `core/models.py`

**Add:**
```python
@dataclass
class ToolCall:
    tool: str
    arguments: dict
    reasoning: str = ""   # from the assistant message before the tool call

@dataclass
class ToolResult:
    tool: str
    arguments: dict
    success: bool
    output: str
```

**Modify `Directive`:**
- Remove `max_replan_rounds: int`
- Add `max_steps: int = 50`

**Modify `ModelBindingPoint`:**
- Rename `PLANNING` → `EXECUTION`

**Modify `Task`:**
- Rename `plan: str` → `execution_trace: str` (serialized list of ToolCall + ToolResult pairs)
- Remove `replan_history: str`
- Keep `branch_name`, `pr_url` — the agent still sets these, just via tools instead of orchestrator code

**Remove:**
- `PlanStep`
- `TaskPlan`
- `ExecutionRound`

---

### 3. `execution/tools/` ← new module

Tools are organized by category. Each file registers its handlers into a shared `ToolRegistry`.

```
execution/tools/
├── __init__.py      # ToolRegistry, LoopState, tool_schemas()
├── filesystem.py    # read_file, list_directory, search_files,
│                    # edit_file, create_file, delete_file
├── shell.py         # run_command
├── git.py           # git_create_worktree, git_commit, git_push, git_create_pr
└── control.py       # finish
```

All handlers share a common signature: `(arguments: dict, state: LoopState) -> ToolResult`

`LoopState` carries the mutable context the tools need:
```python
@dataclass
class LoopState:
    root_workspace: Path        # the original workspace root, never changes
    active_workspace: Path      # starts as root; updated to worktree path after git_create_worktree
    worktree_path: Path | None  # set by git_create_worktree
    branch_name: str            # set by git_create_worktree
    pr_url: str                 # set by git_create_pr
    safety: SafetyPolicy
    directive: Directive
    git: GitWorkflow
    task_id: str
```

`git_create_worktree` updates `state.active_workspace` and `state.worktree_path`. All subsequent filesystem tools resolve paths relative to `state.active_workspace` — the agent does not need to track the path change explicitly.

`ToolRegistry` maps tool name → handler. Unknown tool names return `ToolResult(success=False, output="unknown tool: <name>")`.

**`execution/tools/filesystem.py`** — implements `read_file`, `list_directory`, `search_files`, `write_file`, `edit_file`, `delete_file`.
- Read operations apply path containment check only.
- Write operations apply path containment + forbidden path check.
- `write_file`: guards against overwriting existing files unless `overwrite=true`.
- `edit_file`: fails explicitly if `old_string` appears zero times (not found) or more than once (ambiguous); both are actionable errors the agent can correct.

**`execution/tools/shell.py`** — delegates to `safety.check_command()` before execution. Runs via `subprocess.run()` with timeout from `directive`.

**`execution/tools/git.py`** — thin wrappers over `execution/git_ops.py`. `git_create_worktree` also updates `state.active_workspace`.

**`execution/tools/control.py`** — `finish(summary)` records the summary and signals loop termination. No side effects.

---

### 4. `execution/loop.py` ← new file

```python
class ReActLoop:
    def __init__(
        self,
        llm: LLMClient,
        tool_registry: ToolRegistry,
        constitution: Constitution,
        observer: Observer,
        shutdown_event: threading.Event,
    ): ...

    def run(
        self,
        task: Task,
        workspace: Path,
        directive: Directive,
        experience_context: str,
    ) -> tuple[bool, list[ToolResult]]:
        """
        Returns (success, trace).
        success=False on max_steps, token budget, shutdown, or unrecoverable error.
        """
```

Loop body:

```
state = LoopState(root_workspace=workspace, active_workspace=workspace, ...)
messages = [system_message(task, constitution, experience_context), initial_user_message(task)]

loop:
  check shutdown → break if set
  _, tool_calls = llm.generate_with_tools(messages, tool_registry.schemas())
  for tool_call in tool_calls:
    constitution.check_action_allowed(tool_call.tool, tool_call.arguments)
      blocked → append error result, continue
    result = tool_registry.execute(tool_call, state)
    append assistant turn + tool result turn to messages
    append result to trace
    observer.execute_step(task.id, tool_call, result)
    if tool_call.tool == "finish": return (True, trace)
  if len(trace) >= directive.max_steps: return (False, trace)
  if token_budget_exceeded: return (False, trace)
```

---

### 5. `llm/prompts/react_execute.txt` ← new file

System prompt template. Rendered once at loop start. Contains:
- Task description and workspace root
- All tool schemas with argument descriptions and examples
- Constitution summary (injected)
- Experience context (injected)
- Guidance: read before writing; use worktree when modifying source code; verify before finishing
- How to call `finish`

---

### 6. `agent.py` — simplified

**Remove entirely:**
- `_plan_execute_verify_loop()`
- `_append_replan_round()`
- `_is_task_token_budget_exceeded()`
- `_continue_verification_after_human_resolution()` — agent handles re-verification via tools
- All worktree management code (moved into `git_create_worktree` tool)

**`_execute_single_task()` becomes:**

```python
def _execute_single_task(self, task, directive, constitution) -> bool:
    task_start_time = time.monotonic()
    token_tracker = _get_tracker(self.llm)
    token_before = token_tracker.snapshot() if token_tracker else None

    experience_context = self._get_experience_context(task)

    state = LoopState(
        root_workspace=self.workspace,
        active_workspace=self.workspace,
        safety=self.safety,
        directive=directive,
        git=self.git,
        task_id=task.id,
    )
    loop = ReActLoop(
        llm=client_for_point(self.llm, ModelBindingPoint.EXECUTION.value),
        tool_registry=ToolRegistry(state),
        constitution=constitution,
        observer=self.obs,
        shutdown_event=self._shutdown,
    )
    task.status = TaskStatus.EXECUTING.value
    self.store.update_task(task)

    success, trace = loop.run(task, self.workspace, directive, experience_context)

    task.execution_trace = serialize_trace(trace)
    task.branch_name = state.branch_name
    task.pr_url = state.pr_url or ""
    task.status = TaskStatus.COMPLETED.value if success else TaskStatus.NEEDS_HUMAN.value
    self._finalize_costs(task, task_start_time, token_tracker, token_before)
    self.store.update_task(task)

    if success:
        self.obs.task_completed(task.id, task.title)
    else:
        self.obs.task_needs_human(task.id, "loop ended without finish()")

    self._extract_and_store_learnings(task, "completed" if success else "failed")
    self._maybe_consolidate_experience()
    return success
```

---

### 7. Remove

- `execution/planner.py`
- `execution/executor.py`
- `execution/verifier.py` — agent runs tests via `run_command`; external verifier is redundant
- `llm/prompts/plan_task.txt` and replan prompt variants

---

### 8. `docs/design/execution.md`

Rewrite to reflect the new loop model, tool set, `LoopState`, and the principle that the agent owns its own workflow.

---

## Migration Notes

- `tasks.db` columns `plan`, `replan_history` become `execution_trace` and unused respectively. Add `execution_trace` column via migration; leave old columns in place.
- `Directive.max_replan_rounds` in existing `directive.json` is ignored; `max_steps` defaults to 50.
- `ModelBindingPoint.PLANNING` references in existing model bindings DB become `EXECUTION` via a one-time migration.
- Dashboard task detail view renders `execution_trace` as a tool call timeline; existing `plan` display can be repurposed.

## Verification

- [ ] Unit tests for each tool category: `tools/filesystem.py`, `tools/shell.py`, `tools/git.py`, `tools/control.py`
- [ ] Test `git_create_worktree` updates `state.active_workspace` and subsequent file tools operate in the worktree
- [ ] Unit test for `ArkAdapter.generate_with_tools` against a recorded API response
- [ ] Unit test for `ReActLoop`: finish signal, max_steps termination, constitution block, shutdown signal
- [ ] Integration test: task with file edits → agent creates worktree → commits → PR created
- [ ] Integration test: read-only task → no worktree created, no commit
- [ ] Existing `test_v2_*.py` tests pass
- [ ] `llm_audit.jsonl` records every tool-turn LLM call

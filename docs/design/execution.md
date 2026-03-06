# Execution Module Design

> Module: `src/llm247_v2/execution/`
> Last updated: 2026-03-05

## Purpose

The execution module takes a queued task and carries it through planning, safe execution, verification, and git shipping. It is the part of the agent that actually changes the codebase.

## Pipeline

```
queued task
    │
    ▼
planner.py          — LLM generates a structured execution plan
    │
    ▼
constitution check  — every plan step checked against immutable safety rules
    │ (blocked → NEEDS_HUMAN)
    ▼
git_ops.py          — create isolated git worktree on a fresh branch
    │
    ▼
executor.py         — execute each plan step (edit_file, create_file, run_command, delete_lines)
    │ (step fails → NEEDS_HUMAN)
    ▼
verifier.py         — post-execution checks (syntax, tests, secret scan)
    │ (fails → NEEDS_HUMAN)
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

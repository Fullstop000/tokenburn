# Core Module Design

> Module: `src/llm247_v2/core/`
> Files: `models.py`, `constitution.py`, `directive.py`
> Last updated: 2026-03-05

## Purpose

The `core` package defines the foundational data layer that every other module depends on. It has no dependencies on other `llm247_v2` subpackages — it is the shared vocabulary of the entire system.

Three concerns live here:
- **Models** — the data structures that flow between modules
- **Constitution** — the agent's immutable identity and safety boundaries
- **Directive** — the human's runtime control over agent behavior

## Models (`models.py`)

### Core Types

**`Task`** — the central unit of work. Every discovered task is a `Task`, and every module that touches it reads from or writes to this object.

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | sha256-derived 12-char identifier |
| `title` | str | Human-readable task name |
| `description` | str | Full task description |
| `source` | str | `TaskSource` enum value |
| `status` | str | `TaskStatus` enum value |
| `priority` | int | 1 (highest) – 5 (lowest) |
| `branch_name` | str | Git branch created for this task |
| `pr_url` | str | GitHub PR URL after shipping |
| `plan` | str | JSON-serialized `TaskPlan` |
| `execution_log` | str | Step-by-step execution output |
| `verification_result` | str | Post-execution check results |
| `error_message` | str | Failure reason (if any) |
| `token_cost` | int | Total tokens consumed |
| `time_cost_seconds` | float | Wall-clock execution time |
| `whats_learned` | str | Formatted experience extracted from this task |
| `human_help_request` | str | Structured help request shown in dashboard |

**Task Status Machine:**

```
DISCOVERED → QUEUED → PLANNING → EXECUTING → VERIFYING → COMPLETED
                                     │               │
                                     └───────────────┴──→ NEEDS_HUMAN → HUMAN_RESOLVED → VERIFYING
                                                                                              │
                                                                                        COMPLETED / NEEDS_HUMAN
```

`CANCELLED` is a terminal state reachable from any non-terminal state via the dashboard.

**`TaskSource`** — where a task was found:
`todo_scan`, `lint_check`, `test_gap`, `self_improvement`, `manual`, `backlog`, `github_issue`, `dep_audit`, `web_search`, `interest_driven`

**`TaskPlan`** — the execution plan produced by the planner:

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | str | Parent task |
| `steps` | List[PlanStep] | Ordered list of actions |
| `commit_message` | str | Conventional Commits format |
| `pr_title` | str | GitHub PR title |
| `pr_body` | str | GitHub PR description |

**`PlanStep`** — one atomic action:

| Field | Description |
|-------|-------------|
| `action` | `edit_file` / `create_file` / `run_command` / `delete_lines` |
| `target` | File path or shell command |
| `content` | New file content or line spec |
| `description` | Human-readable intent |

**`Directive`** — runtime behavior configuration (see below).

**`CycleReport`** — summary of one agent cycle: discovered/executed/completed/failed counts, status, timing.

## Constitution (`constitution.py`)

### Purpose

The constitution defines the agent's immutable identity: its mission, operating principles, safety hard limits, and decision priorities. It is loaded from `constitution.md` at the start of every cycle and governs every plan and action.

The constitution is **immutable at runtime** — `constitution.md` and `safety.py` are in `IMMUTABLE_PATHS` and cannot be modified by the agent itself.

### Structure

`Constitution` is a frozen dataclass with these fields:

| Field | Populated from `constitution.md` section |
|-------|------------------------------------------|
| `mission` | `## Mission` |
| `principles` | `## Core Principles` (bullet list) |
| `quality_standards` | `## Quality Standards` |
| `safety_hard_limits` | `## Hard Limits` |
| `safety_soft_limits` | `## Soft Limits` |
| `self_modification_rules` | `## Self-Modification Protocol` (numbered) |
| `decision_priorities` | `## Decision Framework` (numbered) |
| `exploration_philosophy` | `## Exploration Philosophy` |

If the file is missing or unparseable, hardcoded defaults apply:
- Principles: Value first, Minimal change, Understand before acting, Reversibility, Transparency
- Hard limits: Never force push, Never modify secret/credential files, Never merge PRs directly
- Decisions: Safety > Features, Correctness > Speed, Simplicity > Cleverness

### `check_action_allowed(action_type, target_path)`

Called for every plan step before execution begins. Returns `(allowed: bool, reason: str)`.

Blocks:
- Any modification to `IMMUTABLE_PATHS` (`constitution.md`, `safety.py`)
- `delete_file` / `delete_lines` if a hard limit contains "no delete" or "never delete"
- Any modification to `.env`, `.env.*`, or files with "credential" / "secret" in the name

### Prompt Rendering

`to_compact_prompt()` — used in `plan_task.txt` to inject constitution constraints into every planning call (token-efficient, top 3 principles + 4 hard limits).

`to_system_prompt()` — full rendering for contexts where token budget is less constrained.

## Directive (`directive.py`)

### Purpose

The directive is the human's runtime control interface. Unlike the constitution (immutable), the directive can be changed at any time via the dashboard or by editing `.llm247_v2/directive.json`. The agent re-loads it at the start of every cycle.

### Fields

| Field | Default | Description |
|-------|---------|-------------|
| `paused` | false | If true, agent skips execution and sleeps |
| `focus_areas` | `["code_quality", "testing", "documentation"]` | Topics to prioritize in discovery |
| `forbidden_paths` | `[".env", ".git", "credentials.json"]` | Paths the agent must never touch |
| `max_file_changes_per_task` | 10 | Plan step count cap |
| `custom_instructions` | "" | Free-text instructions injected into planning prompt |
| `task_sources` | see below | Per-source enable/priority config |
| `poll_interval_seconds` | 120 | Sleep between cycles |

### Persistence

- Loaded: `load_directive(path)` — returns `default_directive()` if file missing or corrupt
- Saved: `save_directive(path, directive)` — atomic write via `.tmp` + rename
- Rendered: `directive_to_prompt_section(directive)` — injected into `plan_task.txt`

### Design Constraint

All runtime behavior tuning goes through the directive. Never hardcode behavioral switches in agent code. If a behavior needs to be toggled, it belongs in the directive.

# Dashboard Module Design

> Module: `src/llm247_v2/dashboard/`
> File: `server.py`
> Last updated: 2026-03-05

## Purpose

The dashboard is the human control plane for the agent. It exposes an HTTP server with a JSON API and a pre-built frontend (Vite/React), giving operators visibility into what the agent is doing and control over its behavior — all without touching config files or the database directly.

## Architecture

```
Browser / curl
      │
      ▼
ThreadingHTTPServer (BaseHTTPRequestHandler)
      │
      ├── GET  /api/*          → JSON API handlers
      ├── POST /api/*          → mutation handlers
      ├── GET  /               → serves Vite-built index.html
      └── GET  /assets/*       → serves Vite build artifacts
```

The server runs in its own thread when launched with `--with-ui`. It shares the same `TaskStore` and `ExperienceStore` instances as the agent thread, protected by their internal locks.

## API Reference

### Read Endpoints (GET)

| Endpoint | Query params | Description |
|----------|-------------|-------------|
| `/api/tasks` | — | All tasks (newest first, limit 200) |
| `/api/tasks/<id>` | — | Single task with full fields + event log |
| `/api/cycles` | — | Recent 50 cycles |
| `/api/stats` | — | Aggregate counts: total tasks by status, cycles, tokens |
| `/api/help-center` | — | All `needs_human` tasks |
| `/api/experiences` | `limit`, `category`, `q` | Experience store contents |
| `/api/directive` | — | Current directive as JSON |
| `/api/activity` | `limit`, `phase` | Recent activity events from `activity.jsonl` |
| `/api/llm-audit` | `limit`, `seq_after` | Recent LLM calls (previews only, no full prompts) |
| `/api/llm-audit/<seq>` | — | Single LLM call with full prompt + response |

### Write Endpoints (POST)

| Endpoint | Body | Description |
|----------|------|-------------|
| `/api/directive` | `Directive` JSON | Replace directive entirely |
| `/api/pause` | — | Set `directive.paused = true` |
| `/api/resume` | — | Set `directive.paused = false` |
| `/api/tasks/cancel` | `{task_id}` | Cancel a non-terminal task |
| `/api/tasks/inject` | `{title, description, priority}` | Create a manual task |
| `/api/help-center/resolve` | `{task_id, resolution}` | Resolve a `needs_human` task → sets status to `human_resolved` |

### `/api/experiences` Query Modes

Three mutually exclusive modes, in priority order:
1. `q=<text>` → keyword search across summary/detail/tags
2. `category=<name>` → filter by experience category
3. (neither) → return most recent experiences

## Human Help Center Flow

The help center is the primary human-agent interaction point.

```
Agent hits a blocker (constitution, execution failure, verification failure)
    │
    ▼
task.status = NEEDS_HUMAN
task.human_help_request = structured text:
    ## Task: <title>
    ## Blocked at: <phase>
    ### What happened
    ### Error detail
    ### Suggested actions
    │
    ▼
Dashboard GET /api/help-center shows the task
    │
    ▼
Human inspects, fixes (edits files, adjusts config, etc.)
    │
    ▼
POST /api/help-center/resolve {task_id, resolution}
    │
    ▼
task.status = HUMAN_RESOLVED
    │
    ▼
Next agent cycle picks it up via get_next_executable_task()
(human_resolved tasks have priority over queued tasks)
    │
    ▼
Agent re-runs verification (skips planning and execution)
```

## Frontend

The frontend is a Vite/React build. Build artifacts live in `frontend/dist/`. The server reads `frontend/dist/index.html` and serves `frontend/dist/assets/` statically.

If `frontend/dist/` doesn't exist, the server falls back to a minimal HTML page with build instructions.

Path traversal protection: `_resolve_frontend_asset_path()` validates that the resolved path is under `frontend/dist/` before serving.

## Activity & LLM Audit Reads

Both `activity.jsonl` and `llm_audit.jsonl` are append-only files. The dashboard reads them via `_read_jsonl_tail(path, limit)` — seeks to the end of the file and reads the last N lines. This is efficient for large files without loading everything into memory.

`/api/llm-audit` strips `prompt_full` and `response_full` from list responses (large fields). Only `/api/llm-audit/<seq>` returns the full text, for the detail view.

## Design Constraints

- **Read-only for most state** — the server reads `TaskStore` and `ExperienceStore` directly. It only mutates via well-defined POST endpoints, which call the stores' write methods.
- **No auth** — the dashboard binds to `127.0.0.1` by default. Exposing it externally requires explicit `--ui-host` override and is the operator's responsibility to secure.
- **CORS open** — `Access-Control-Allow-Origin: *` on all API responses, for local development convenience.
- **Experience store is optional** — if `experience_store=None`, `/api/experiences` returns an empty list without error.

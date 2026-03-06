# Storage Module Design

> Module: `src/llm247_v2/storage/`
> Files: `store.py`, `experience.py`
> Last updated: 2026-03-05

## Purpose

The `storage` package handles all SQLite persistence. It is split into two stores with separate databases:

- **`TaskStore`** (`store.py`, `tasks.db`) — tasks, events, and cycle history. The operational database.
- **`ExperienceStore`** (`experience.py`, `experience.db`) — long-term learnings. See [experience.md](experience.md) for full design.

Separating the databases lets each be independently backed up, inspected, or reset without affecting the other.

## TaskStore (`store.py`)

### Schema

**`tasks` table** — one row per task, updated in-place as the task progresses through its lifecycle.

```sql
CREATE TABLE tasks (
    id                  TEXT PRIMARY KEY,   -- sha256-derived 12-char id
    title               TEXT NOT NULL,
    description         TEXT,
    source              TEXT NOT NULL,      -- TaskSource enum value
    status              TEXT NOT NULL,      -- TaskStatus enum value
    priority            INTEGER,            -- 1 (highest) to 5 (lowest)
    created_at          TEXT,               -- ISO 8601 UTC
    updated_at          TEXT,               -- ISO 8601 UTC, updated on every write
    branch_name         TEXT,
    pr_url              TEXT,
    plan                TEXT,               -- JSON-serialized TaskPlan
    execution_log       TEXT,               -- step-by-step execution output
    verification_result TEXT,
    error_message       TEXT,
    cycle_id            INTEGER,
    token_cost          INTEGER,
    time_cost_seconds   REAL,
    whats_learned       TEXT,               -- formatted experience summary
    human_help_request  TEXT                -- structured help request for dashboard
);
```

**`task_events` table** — append-only event log per task. Used for audit trail and dashboard detail view.

```sql
CREATE TABLE task_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL,
    event_type  TEXT NOT NULL,    -- e.g. "cancelled", "human_resolved", "injected"
    detail      TEXT,
    created_at  TEXT
);
```

**`cycles` table** — one row per agent cycle.

```sql
CREATE TABLE cycles (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at        TEXT NOT NULL,
    completed_at      TEXT,
    tasks_discovered  INTEGER,
    tasks_executed    INTEGER,
    tasks_completed   INTEGER,
    tasks_failed      INTEGER,
    status            TEXT,    -- "running" | "completed"
    summary           TEXT
);
```

### Concurrency

`TaskStore` uses a single `threading.Lock` around every write. The connection is opened with `check_same_thread=False` and `PRAGMA journal_mode=WAL` to allow concurrent reads from the dashboard thread while the agent writes.

### Key Query Patterns

**Next task to execute** — `get_next_executable_task()` prioritizes `human_resolved` tasks over `queued` tasks, then sorts by `priority ASC, created_at ASC`. This ensures tasks unblocked by human intervention are retried immediately.

**Deduplication at insert** — `insert_task()` uses `INSERT OR IGNORE`. Title-based deduplication is done before calling this, in `agent._phase_discover()`, by comparing against the set of existing task titles.

**Stats for dashboard** — `get_stats()` returns status counts, total cycle count, and total token spend in a single query.

### Migrations

`_MIGRATIONS` is a list of `ALTER TABLE` statements. They run at startup via `_run_migrations()`, which silently ignores `OperationalError` (column already exists). This is the schema evolution mechanism — new columns are added here without touching the main `_SCHEMA`.

Current migrations:
- Add `token_cost`
- Add `time_cost_seconds`
- Add `whats_learned`
- Add `human_help_request`

### API Surface

| Method | Description |
|--------|-------------|
| `insert_task(task)` | Insert new task (INSERT OR IGNORE) |
| `update_task(task)` | Full task update, bumps `updated_at` |
| `get_task(task_id)` | Single task by id |
| `list_tasks(status, limit, offset)` | List tasks, optionally filtered by status |
| `get_next_executable_task()` | Next task to execute (human_resolved first, then queued) |
| `list_human_help_tasks(limit)` | All `needs_human` tasks for the help center |
| `add_event(task_id, event_type, detail)` | Append event to audit trail |
| `get_events(task_id, limit)` | Task event history |
| `start_cycle()` | Insert new cycle row, return cycle_id |
| `complete_cycle(cycle_id, ...)` | Update cycle with final counts |
| `get_recent_cycles(limit)` | Recent cycle history |
| `get_stats()` | Aggregate stats for dashboard |

## Design Constraints

- **Single connection per store** — both `TaskStore` and `ExperienceStore` open one persistent connection, protected by a `threading.Lock`. No connection pooling needed at this scale.
- **WAL mode always on** — ensures the dashboard HTTP thread can read while the agent writes, without blocking.
- **No ORM** — raw SQL with `sqlite3.Row`. Keeps the dependency footprint minimal and queries explicit.
- **Separate databases** — `tasks.db` and `experience.db` are in the same `.llm247_v2/` directory but are independent SQLite files. This allows resetting experience without affecting task history, and vice versa.

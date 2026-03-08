# Plan: Human-Agent Interaction via Native Dashboard Inbox

> Status: In Progress
> Created: 2026-03-07
> Completed:
> PR: https://github.com/Fullstop000/sprout/pull/14
> Proposal: [docs/proposals/2026-03-07-human-agent-interaction.md](../proposals/2026-03-07-human-agent-interaction.md)

## Goal

Replace the one-shot `human_help_request` / `human_resolved` handoff with a bidirectional interaction model backed by a native SQLite inbox. The agent opens threads when blocked (Shape A) and picks up human-opened threads as tasks (Shape B). All interaction is self-contained — no external services required.

> **Implementation note:** The original proposal planned GitHub Issues as the primary surface. During implementation this was replaced with a native dashboard inbox. This eliminates the GitHub token requirement and gives humans a built-in UI inside the dashboard itself.

## Scope

- New storage: `src/llm247_v2/storage/thread_store.py` — threads, messages, thread_tasks
- Agent integration: open/update/close threads on task state transitions
- Dashboard API: thread CRUD endpoints served alongside existing routes
- Dashboard UI: `InboxPage` — thread list with batch selection, message chat, reply + close button group
- No external dependencies added

Out of scope: real-time push, GitHub mirroring, ambient directives (Shape C).

---

## Data Model

### `ThreadStore` — `threads.db`

```sql
CREATE TABLE IF NOT EXISTS threads (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT DEFAULT 'open',
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    thread_id   TEXT NOT NULL,
    role        TEXT NOT NULL,   -- 'agent' | 'human'
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY(thread_id) REFERENCES threads(id)
);

CREATE TABLE IF NOT EXISTS thread_tasks (
    thread_id   TEXT NOT NULL,
    task_id     TEXT NOT NULL,
    PRIMARY KEY (thread_id, task_id),
    FOREIGN KEY(thread_id) REFERENCES threads(id)
);
```

**Thread statuses:**

| status | Meaning |
|--------|---------|
| `open` | Created by human (Shape B); agent hasn't acted yet |
| `waiting_reply` | Agent posted a message and is waiting for human response |
| `replied` | Human responded; agent hasn't processed next cycle yet |
| `closed` | Interaction complete; linked tasks resolved or cancelled |

---

## API Endpoints

All endpoints served by `src/llm247_v2/dashboard/server.py`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/threads` | List threads; optional `?status=` filter |
| `GET` | `/api/threads/<id>` | Thread detail with messages and linked task ids |
| `POST` | `/api/threads` | Create thread (human-initiated); queues a task |
| `POST` | `/api/threads/<id>/reply` | Post a human reply; transitions status to `replied` |
| `POST` | `/api/threads/<id>/close` | Close thread; cancels linked tasks in `needs_human`/`queued` |
| `POST` | `/api/threads/bulk-close` | Close multiple threads by id list |

Thread data is also surfaced in `GET /api/tasks/<id>` (includes linked thread summary if present).

---

## Agent Integration

### Shape A — Agent opens thread when blocked

When a task transitions to `needs_human`, the agent creates a thread with a structured message (what was tried, what failed, what is needed) and links the task via `thread_tasks`.

### Shape B — Human opens thread as task request

Human creates a thread via the dashboard. The agent's next cycle detects `open` threads with no linked tasks, creates a `Task` (`source=thread`), links it, and posts an acknowledgement message.

### On human reply

Agent detects `replied` threads on the next cycle. Linked `needs_human` tasks are re-queued as `human_resolved`; the thread status transitions back to `waiting_reply` when the agent responds.

### On task completion or failure

Agent updates the thread to `closed` and posts a completion or failure summary.

---

## Dashboard UI

`frontend/src/pages/InboxPage.tsx` — full-page inbox with:

- **Thread list** (left panel, scrollable): active and closed sections; "Select all" + per-row checkboxes; batch action bar ("Close N"); compact status badges
- **Thread detail** (right panel): message chat (agent / human bubbles); task id chips that open a task detail modal; inline close-reason form; **Close | Send** button group in the reply area
- **New thread form**: collapsible inline form in the thread list toolbar

`frontend/src/api/dashboardApi.ts` exposes all thread endpoints as typed methods.

`App.tsx` wires thread state, handlers (`replyToThread`, `closeThread`, `bulkCloseThreads`, `createThread`), and auto-refresh every 3s when inbox is active.

---

## File Checklist

- [x] `src/llm247_v2/storage/thread_store.py`
- [x] `src/llm247_v2/dashboard/server.py` — thread API routes
- [x] `src/llm247_v2/agent.py` — thread open/update/close on task transitions
- [x] `src/llm247_v2/__main__.py` — construct `ThreadStore`, pass to server and agent
- [x] `frontend/src/pages/InboxPage.tsx`
- [x] `frontend/src/api/dashboardApi.ts` — thread methods
- [x] `frontend/src/App.tsx` — thread state + handlers
- [x] `frontend/src/types/dashboard.ts` — `ThreadSummary`, `ThreadDetail`, `ThreadMessage`
- [x] `tests/test_v2_dashboard.py` — thread API unit tests

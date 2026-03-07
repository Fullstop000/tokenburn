# Plan: Human-Agent Interaction via GitHub Issues

> Status: Approved
> Created: 2026-03-07
> Completed:
> PR:
> Proposal: [docs/proposals/2026-03-07-human-agent-interaction.md](../proposals/2026-03-07-human-agent-interaction.md)

## Goal

Replace the one-shot `human_help_request` / `human_resolved` handoff with a bidirectional interaction model backed by GitHub Issues. The agent opens issues when blocked (Shape A) and picks up human-opened issues as tasks (Shape B). An internal SQLite mirror enables fast local reads and dashboard display without repeated GitHub API calls.

## Scope

- New module: `src/llm247_v2/github/` — GitHub API client + issue sync
- New storage: `src/llm247_v2/storage/thread_store.py` — threads, messages, thread_tasks mirror
- Model change: `Task.github_issue_url` field
- Agent cycle: new `_phase_sync_github_issues` phase (runs before discovery)
- Agent execution: open/comment/close GitHub Issues on task state transitions
- Dashboard: thread display in task detail view
- Config: GitHub token, repo coordinates, assignees, label name

Out of scope: Shape C (ambient directives), real-time push, non-GitHub deployments.

---

## GitHub Issue Labels

Three labels, all managed by the agent. The `sprout` label is the only one humans ever need to apply manually (for Shape B).

| Label | Meaning | Who applies |
|-------|---------|-------------|
| `sprout` | Marks an issue as Sprout-managed; the agent only scans issues with this label | Shape A: agent on create; Shape B: human on create |
| `needs-human` | Agent is blocked and waiting for human response | Agent on block; agent removes on human reply |
| `in-progress` | Agent is actively executing the linked task(s) | Agent on pickup; agent removes on completion/failure |

---

## Issue Title Format

**Shape A** (agent opens when blocked):
```
[sprout] blocked: {task_title}
```

**Shape B** (human opens to request work):
Free-form — the agent uses the title as the task title verbatim. No format is enforced.

---

## Issue Body and Comment Templates

### Shape A — Initial blocked issue body

```markdown
## Blocked: {task_title}

**Task:** `{task_id}` | **Source:** {source} | **Branch:** `{branch_name}`
**Dashboard:** {dashboard_url}/tasks/{task_id}

## What I tried
{last 20 lines of execution_log}

## Where I'm stuck
{human_help_request — the specific blocker}

## What I need
- [ ] {specific ask 1}
- [ ] {specific ask 2}

---
*Reply to this issue to unblock execution. Sprout will pick up your response on the next cycle (~2 min).*
```

### Shape B — Agent acknowledgement comment (on pickup)

```markdown
Picked up as task `{task_id}`. Starting execution.
```

If decomposed into multiple sub-tasks:
```markdown
Decomposed into {N} sub-tasks: `{t1}`, `{t2}`, `{t3}`. Starting execution.
```

### Completion comment + close

```markdown
**Completed** ✓

{execution summary}

PR: {pr_url}
```

### Still blocked (same issue, attempt N)

```markdown
**Still blocked** (attempt {n})

{updated blocker description}

{updated ask}
```

### Abandoned after N attempts — close as `not_planned`

```markdown
**Giving up** after {N} attempts.

Last error: {error_message}

Task `{task_id}` marked as failed. Re-open this issue after resolving the underlying problem and Sprout will retry.
```

### Human closed issue — agent acknowledgement comment

```markdown
Acknowledged. Task `{task_id}` has been cancelled.
```

---

## Assign to Human

When the agent opens a blocked issue (Shape A), it assigns the issue to the configured human(s):

```
GITHUB_ASSIGNEES=username1,username2   # comma-separated, read from env
```

Shape B issues are opened by humans themselves; no assignment needed.

---

## GitHub Issue State Machine

The thread's `status` field in ThreadStore tracks Sprout's view of each issue's lifecycle.

### States

| status | Meaning |
|--------|---------|
| `pending` | Issue mirrored, no task created yet (Shape B awaiting agent pickup) |
| `linked` | Task(s) created and associated; task is queued or executing |
| `awaiting_human` | Task is `needs_human`; issue has `needs-human` label; waiting for reply |
| `human_responded` | New human comment detected; agent will re-queue task on next cycle |
| `closed_completed` | All linked tasks completed; issue closed with summary |
| `closed_cancelled` | Human closed issue; all linked tasks cancelled |
| `closed_abandoned` | Consecutive block limit reached; agent gave up; issue closed as `not_planned` |

### Transition Table

| Event | From | To | GitHub action | Task action |
|-------|------|----|---------------|-------------|
| Agent detects new `sprout`-labelled issue | `pending` | `linked` | Add `in-progress` label; comment acknowledgement | Create Task(s), `source=github_issue`, `queued` |
| Task executes successfully | `linked` | `closed_completed` | Comment completion summary; remove `in-progress`; close issue | → `completed` |
| Task hits blocker (first time, no existing issue) | — | `awaiting_human` | Open new issue (Shape A); add `needs-human` + assign | → `needs_human` |
| Task hits blocker (issue already exists) | `linked` | `awaiting_human` | Comment "still blocked (attempt N)"; ensure `needs-human` label | → `needs_human` |
| Human comments on issue | `awaiting_human` | `human_responded` | Agent removes `needs-human` label | — |
| Agent picks up human reply | `human_responded` | `linked` | — | → `human_resolved` → re-queued |
| Human manually closes issue | any open | `closed_cancelled` | Agent comments acknowledgement | → `cancelled` |
| Consecutive blocks ≥ N | `awaiting_human` | `closed_abandoned` | Comment "giving up"; close as `not_planned` | → `failed` |
| Human re-opens a closed issue | `closed_*` | `pending` (new thread) | Agent treats as new Shape B request | Create new Task |

### State diagram

```
              [human opens issue]
                     │
                  pending ──[human closes before pickup]──► closed_cancelled
                     │
              [agent creates task(s)]
                     │
                  linked ──[task succeeds]──────────────► closed_completed
                     │
              [task blocked]
                     │
               awaiting_human ──[human closes]──────────► closed_cancelled
                     │
         ┌───────────┤
         │           │
  [human replies]    [N consecutive blocks]
         │           │
  human_responded    closed_abandoned
         │
  [agent re-queues]
         │
       linked  (loop back)
```

---

## Data Model

### `Task` — one new field

```python
@dataclass
class Task:
    ...
    github_issue_url: str = ""   # URL of the linked GitHub Issue, if any
```

DB migration:
```sql
ALTER TABLE tasks ADD COLUMN github_issue_url TEXT DEFAULT ''
```

### `ThreadStore` — new SQLite file (`threads.db`)

```sql
-- One row per GitHub Issue (mirror)
CREATE TABLE threads (
    id                    TEXT PRIMARY KEY,   -- internal UUID
    github_issue_number   INTEGER NOT NULL,
    github_issue_url      TEXT NOT NULL,
    github_issue_title    TEXT NOT NULL,
    status                TEXT DEFAULT 'pending',
    created_by            TEXT NOT NULL,      -- 'agent' | 'human'
    last_synced_at        TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

-- One row per GitHub comment (+ issue body as comment_id=0)
CREATE TABLE messages (
    id                  TEXT PRIMARY KEY,
    thread_id           TEXT NOT NULL,
    role                TEXT NOT NULL,        -- 'human' | 'agent'
    body                TEXT NOT NULL,
    github_comment_id   INTEGER DEFAULT 0,    -- 0 = issue body itself
    created_at          TEXT NOT NULL,
    FOREIGN KEY(thread_id) REFERENCES threads(id)
);

-- Junction table: one issue can link to many tasks (decomposition)
CREATE TABLE thread_tasks (
    thread_id   TEXT NOT NULL,
    task_id     TEXT NOT NULL,
    role        TEXT DEFAULT 'primary',   -- 'primary' | 'subtask'
    PRIMARY KEY (thread_id, task_id),
    FOREIGN KEY(thread_id) REFERENCES threads(id)
);

-- Outbox: agent comments queued to be posted back to GitHub
CREATE TABLE pending_comments (
    id          TEXT PRIMARY KEY,
    thread_id   TEXT NOT NULL,
    body        TEXT NOT NULL,
    posted      INTEGER DEFAULT 0,        -- 0=pending, 1=posted
    github_comment_id INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL,
    FOREIGN KEY(thread_id) REFERENCES threads(id)
);

CREATE INDEX idx_threads_status   ON threads(status);
CREATE INDEX idx_messages_thread  ON messages(thread_id);
CREATE INDEX idx_tt_thread        ON thread_tasks(thread_id);
CREATE INDEX idx_tt_task          ON thread_tasks(task_id);
```

**Relationships:**
- `GitHub Issue ↔ Thread` — 1:1 (mirror)
- `Thread ↔ Task` — 1:N via `thread_tasks` (one issue can spawn multiple sub-tasks)
- `Task → Thread` — N:1 (reverse lookup via `github_issue_url` or `thread_tasks`)

### `ThreadStore` key methods

```python
class ThreadStore:
    # Sync
    def upsert_thread(self, github_issue: dict) -> Thread: ...
    def upsert_message(self, thread_id: str, role: str, body: str,
                       github_comment_id: int, created_at: str) -> Message: ...

    # Task linkage
    def link_task(self, thread_id: str, task_id: str, role: str = "primary") -> None: ...
    def get_tasks_for_thread(self, thread_id: str) -> list[str]: ...
    def get_thread_for_task(self, task_id: str) -> Thread | None: ...

    # Agent workflow
    def get_pending_threads(self) -> list[Thread]: ...
    def get_threads_awaiting_human(self) -> list[Thread]: ...
    def get_human_responded_threads(self) -> list[Thread]: ...
    def get_new_human_messages(self, thread_id: str) -> list[Message]: ...

    # Status updates
    def set_status(self, thread_id: str, status: str) -> None: ...

    # Comment outbox
    def queue_agent_comment(self, thread_id: str, body: str) -> str: ...
    def get_pending_comments(self) -> list[PendingComment]: ...
    def mark_comment_posted(self, comment_id: str, github_comment_id: int) -> None: ...
```

---

## `src/llm247_v2/github/client.py`

Thin `httpx` wrapper over the GitHub Issues REST API.

```python
class GitHubClient:
    def __init__(self, token: str, owner: str, repo: str,
                 label: str = "sprout",
                 assignees: list[str] | None = None) -> None: ...

    def list_open_issues(self, since: str | None = None) -> list[dict]: ...
    # GET /issues?state=open&labels={label}&since={iso}

    def get_issue_comments(self, issue_number: int,
                           since: str | None = None) -> list[dict]: ...
    # GET /issues/{number}/comments?since={iso}

    def create_issue(self, title: str, body: str,
                     assignees: list[str] | None = None,
                     labels: list[str] | None = None) -> dict: ...
    # POST /issues  (always includes self.label)

    def add_labels(self, issue_number: int, labels: list[str]) -> None: ...
    def remove_label(self, issue_number: int, label: str) -> None: ...

    def create_comment(self, issue_number: int, body: str) -> dict: ...
    # POST /issues/{number}/comments

    def close_issue(self, issue_number: int,
                    state_reason: str = "completed") -> None: ...
    # PATCH /issues/{number} — state_reason: 'completed' | 'not_planned'
```

---

## `src/llm247_v2/github/sync.py`

Orchestrates one sync cycle.

```python
@dataclass
class SyncResult:
    new_threads: list[Thread]                          # Shape B: issue → create tasks
    unblocked: list[tuple[Thread, list[Message]]]      # Shape A: human replied → re-queue
    comments_posted: int                               # outbox items sent

def sync_github_issues(
    github: GitHubClient,
    thread_store: ThreadStore,
    task_store: TaskStore,
    since: str | None,
) -> SyncResult:
```

Steps per cycle:
1. Fetch open issues (with `since` cursor)
2. Upsert threads + messages into ThreadStore
3. Detect new human comments on `awaiting_human` threads → add to `unblocked`
4. Detect `pending` threads (no linked task) → add to `new_threads`
5. Detect issues closed by human → set thread to `closed_cancelled`
6. Flush pending_comments outbox to GitHub API

---

## Agent Integration

### `AutonomousAgentV2` constructor additions

```python
def __init__(
    self,
    ...
    github_client: GitHubClient | None = None,
    thread_store: ThreadStore | None = None,
) -> None:
    ...
    self.github = github_client
    self.thread_store = thread_store
    self._last_github_sync: str | None = None
```

### New phase: `_phase_sync_github_issues`

Called first in `run_cycle`, before discovery:

```python
def _phase_sync_github_issues(self) -> SyncResult:
    result = sync_github_issues(
        self.github, self.thread_store, self.store, self._last_github_sync
    )
    self._last_github_sync = _now_iso()

    # Shape B: new issues → create tasks (or sub-tasks if agent decomposes)
    for thread in result.new_threads:
        task = Task(
            id=_new_id(),
            title=thread.github_issue_title,
            description=thread.messages[0].body if thread.messages else "",
            source="github_issue",
            status=TaskStatus.QUEUED.value,
            priority=3,
            github_issue_url=thread.github_issue_url,
        )
        self.store.insert_task(task)
        self.thread_store.link_task(thread.id, task.id)
        self.thread_store.queue_agent_comment(thread.id, f"Picked up as task `{task.id}`. Starting execution.")
        self.obs.task_queued(task.id, task.title, "github_issue")

    # Shape A: human replied → re-queue blocked tasks
    for thread, new_messages in result.unblocked:
        for task_id in self.thread_store.get_tasks_for_thread(thread.id):
            task = self.store.get_task(task_id)
            if task and task.status == TaskStatus.NEEDS_HUMAN.value:
                task.status = TaskStatus.HUMAN_RESOLVED.value
                task.human_help_request = ""
                self.store.update_task(task)
        self.thread_store.set_status(thread.id, "human_responded")

    return result
```

### On task → `needs_human` (in `_execute_single_task`)

```python
if not success and self.github and self.thread_store:
    thread = self.thread_store.get_thread_for_task(task.id)
    if thread:
        # Already has an issue (Shape B or prior Shape A) — comment "still blocked"
        attempt = len([m for m in self.thread_store.get_messages(thread.id)
                       if m.role == "agent"]) + 1
        self.thread_store.queue_agent_comment(
            thread.id, _fmt_still_blocked(task, attempt)
        )
        self.thread_store.set_status(thread.id, "awaiting_human")
    else:
        # No existing issue — open one (Shape A)
        issue = self.github.create_issue(
            title=f"[sprout] blocked: {task.title}",
            body=_fmt_blocked_body(task),
            assignees=self.github.assignees,
            labels=["sprout", "needs-human"],
        )
        task.github_issue_url = issue["html_url"]
        thread = self.thread_store.upsert_thread(issue)
        self.thread_store.link_task(thread.id, task.id)
        self.thread_store.set_status(thread.id, "awaiting_human")
    self.store.update_task(task)
```

### On task → `completed` or `failed` (end of `_execute_single_task`)

```python
if self.github and self.thread_store:
    thread = self.thread_store.get_thread_for_task(task.id)
    if thread:
        all_done = all(
            self.store.get_task(tid).status in (
                TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value
            )
            for tid in self.thread_store.get_tasks_for_thread(thread.id)
        )
        if all_done:
            if success:
                self.thread_store.queue_agent_comment(thread.id, _fmt_completed(task))
                self.github.close_issue(thread.github_issue_number, state_reason="completed")
                self.thread_store.set_status(thread.id, "closed_completed")
            else:
                self.thread_store.queue_agent_comment(thread.id, _fmt_abandoned(task))
                self.github.close_issue(thread.github_issue_number, state_reason="not_planned")
                self.thread_store.set_status(thread.id, "closed_abandoned")
```

### On human-closed issue (detected in sync)

```python
# In _phase_sync_github_issues, after sync:
for thread in closed_by_human_threads:
    self.thread_store.queue_agent_comment(thread.id, _fmt_cancelled(task))
    for task_id in self.thread_store.get_tasks_for_thread(thread.id):
        task = self.store.get_task(task_id)
        if task and task.status not in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value):
            task.status = TaskStatus.CANCELLED.value
            self.store.update_task(task)
    self.thread_store.set_status(thread.id, "closed_cancelled")
```

---

## Bootstrap (`bootstrap.py`)

Read optional GitHub env vars and wire up `GitHubClient` + `ThreadStore`:

```python
GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER    = os.getenv("GITHUB_OWNER")
GITHUB_REPO     = os.getenv("GITHUB_REPO")
GITHUB_LABEL    = os.getenv("GITHUB_LABEL", "sprout")
GITHUB_ASSIGNEES = [a.strip() for a in os.getenv("GITHUB_ASSIGNEES", "").split(",") if a.strip()]

github_client = None
thread_store = None
if GITHUB_TOKEN and GITHUB_OWNER and GITHUB_REPO:
    github_client = GitHubClient(GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO,
                                 label=GITHUB_LABEL, assignees=GITHUB_ASSIGNEES)
    thread_store = ThreadStore(state_dir / "threads.db")
```

GitHub integration is entirely opt-in — the agent runs normally without it.

---

## Dashboard

Extend `_api_task_detail` to include the linked thread:

```python
def _api_task_detail(store, task_id, thread_store=None):
    ...
    result["github_issue_url"] = task.github_issue_url
    result["thread"] = []
    if thread_store:
        thread = thread_store.get_thread_for_task(task_id)
        if thread:
            result["thread"] = [
                {"role": m.role, "body": m.body, "created_at": m.created_at}
                for m in thread_store.get_messages(thread.id)
            ]
    return result
```

Frontend renders the thread as a read-only comment list with `agent` / `human` role badges and a direct link to the GitHub Issue.

---

## Migration Notes

- `Task.github_issue_url` added via `ALTER TABLE` in `store.py` — safe for existing databases
- `ThreadStore` is a new SQLite file (`threads.db`) alongside `tasks.db` — no migration needed
- All GitHub behaviour is gated on `self.github is not None` — existing deployments unaffected

---

## Test Plan

| Layer | What to test |
|-------|-------------|
| `GitHubClient` | Mock `httpx`; assert correct API calls for each method |
| `ThreadStore` | Upsert idempotency; `link_task` / `get_tasks_for_thread`; comment outbox queue/flush |
| `sync_github_issues` | New issue → `new_threads`; human comment → `unblocked`; human close → cancelled; outbox flush |
| Agent cycle — Shape B | Mock client returns open issue → task created, thread linked, ack comment queued |
| Agent cycle — Shape A | Task fails → no thread exists → new issue opened, thread created; task fails again → comment on existing issue |
| Agent cycle — unblock | `human_responded` thread → task re-queued as `human_resolved` |
| Agent cycle — human close | Closed issue detected → linked tasks cancelled |
| Agent cycle — all sub-tasks done | Last task completes → issue closed |
| Dashboard | `thread` field in task detail response when `ThreadStore` populated |

---

## File Checklist

- [ ] `src/llm247_v2/github/__init__.py`
- [ ] `src/llm247_v2/github/client.py`
- [ ] `src/llm247_v2/github/sync.py`
- [ ] `src/llm247_v2/storage/thread_store.py`
- [ ] `src/llm247_v2/core/models.py` — add `github_issue_url` to `Task`
- [ ] `src/llm247_v2/storage/store.py` — migration for `github_issue_url`
- [ ] `src/llm247_v2/agent.py` — `_phase_sync_github_issues`; open/comment/close on state transitions
- [ ] `src/llm247_v2/bootstrap.py` — construct `GitHubClient` + `ThreadStore` from env
- [ ] `src/llm247_v2/dashboard/server.py` — thread in task detail API response
- [ ] `tests/test_v2_github_client.py`
- [ ] `tests/test_v2_thread_store.py`
- [ ] `tests/test_v2_github_sync.py`
- [ ] `tests/test_v2_agent.py` — extend with GitHub interaction scenarios

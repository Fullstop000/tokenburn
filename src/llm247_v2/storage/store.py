from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from llm247_v2.core.models import CycleReport, Task

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'discovered',
    priority INTEGER NOT NULL DEFAULT 3,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    branch_name TEXT DEFAULT '',
    pr_url TEXT DEFAULT '',
    execution_trace TEXT DEFAULT '',
    execution_log TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    cycle_id INTEGER DEFAULT 0,
    token_cost INTEGER DEFAULT 0,
    time_cost_seconds REAL DEFAULT 0.0,
    whats_learned TEXT DEFAULT '',
    human_help_request TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT DEFAULT '',
    tasks_discovered INTEGER DEFAULT 0,
    tasks_executed INTEGER DEFAULT 0,
    tasks_completed INTEGER DEFAULT 0,
    tasks_failed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    summary TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id);
CREATE INDEX IF NOT EXISTS idx_cycles_status ON cycles(status);
"""

_MIGRATIONS = [
    "ALTER TABLE tasks ADD COLUMN token_cost INTEGER DEFAULT 0",
    "ALTER TABLE tasks ADD COLUMN time_cost_seconds REAL DEFAULT 0.0",
    "ALTER TABLE tasks ADD COLUMN whats_learned TEXT DEFAULT ''",
    "ALTER TABLE tasks ADD COLUMN human_help_request TEXT DEFAULT ''",
    # Legacy columns kept for backward compat with existing databases
    "ALTER TABLE tasks ADD COLUMN replan_history TEXT DEFAULT ''",
    "ALTER TABLE tasks ADD COLUMN execution_trace TEXT DEFAULT ''",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_task(row: sqlite3.Row) -> Task:
    d = dict(row)
    return Task(
        id=d["id"],
        title=d["title"],
        description=d["description"],
        source=d["source"],
        status=d["status"],
        priority=d["priority"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        branch_name=d["branch_name"],
        pr_url=d["pr_url"],
        execution_trace=d.get("execution_trace", "") or "",
        execution_log=d["execution_log"],
        error_message=d["error_message"],
        cycle_id=d["cycle_id"],
        token_cost=d.get("token_cost", 0) or 0,
        time_cost_seconds=d.get("time_cost_seconds", 0.0) or 0.0,
        whats_learned=d.get("whats_learned", "") or "",
        human_help_request=d.get("human_help_request", "") or "",
    )


class TaskStore:
    """SQLite-backed store for tasks, events, and cycle history."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._run_migrations()

    def _run_migrations(self) -> None:
        for sql in _MIGRATIONS:
            try:
                self._conn.execute(sql)
                self._conn.commit()
            except sqlite3.OperationalError:
                pass

    def insert_task(self, task: Task) -> None:
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                """INSERT OR IGNORE INTO tasks
                   (id, title, description, source, status, priority,
                    created_at, updated_at, branch_name, pr_url, execution_trace,
                    execution_log, error_message, cycle_id,
                    token_cost, time_cost_seconds, whats_learned, human_help_request)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.id, task.title, task.description, task.source,
                    task.status, task.priority,
                    task.created_at or now, task.updated_at or now,
                    task.branch_name, task.pr_url, task.execution_trace,
                    task.execution_log, task.error_message, task.cycle_id,
                    task.token_cost, task.time_cost_seconds, task.whats_learned,
                    task.human_help_request,
                ),
            )
            self._conn.commit()

    def update_task(self, task: Task) -> None:
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                """UPDATE tasks SET
                   title=?, description=?, source=?, status=?, priority=?,
                   updated_at=?, branch_name=?, pr_url=?, execution_trace=?,
                   execution_log=?, error_message=?, cycle_id=?,
                   token_cost=?, time_cost_seconds=?, whats_learned=?, human_help_request=?
                   WHERE id=?""",
                (
                    task.title, task.description, task.source, task.status,
                    task.priority, now, task.branch_name, task.pr_url,
                    task.execution_trace, task.execution_log,
                    task.error_message, task.cycle_id,
                    task.token_cost, task.time_cost_seconds, task.whats_learned,
                    task.human_help_request, task.id,
                ),
            )
            self._conn.commit()

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return _row_to_task(row) if row else None

    def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Task]:
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM tasks WHERE status=? ORDER BY priority, updated_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [_row_to_task(r) for r in rows]

    def get_next_queued_task(self) -> Optional[Task]:
        """Pick the highest-priority queued task."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE status='queued' ORDER BY priority ASC, created_at ASC LIMIT 1"
            ).fetchone()
        return _row_to_task(row) if row else None

    def get_next_executable_task(self) -> Optional[Task]:
        """Pick the next executable task, prioritizing human-resolved retries."""
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM tasks
                   WHERE status IN ('human_resolved', 'queued')
                   ORDER BY
                     CASE status WHEN 'human_resolved' THEN 0 ELSE 1 END,
                     priority ASC,
                     created_at ASC
                   LIMIT 1"""
            ).fetchone()
        return _row_to_task(row) if row else None

    def has_duplicate(self, title: str, source: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                """SELECT 1 FROM tasks
                   WHERE title=? AND source=? AND status NOT IN ('completed', 'failed', 'cancelled')
                   LIMIT 1""",
                (title, source),
            ).fetchone()
        return row is not None

    def add_event(self, task_id: str, event_type: str, detail: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO task_events (task_id, event_type, detail, created_at) VALUES (?, ?, ?, ?)",
                (task_id, event_type, detail, _now_iso()),
            )
            self._conn.commit()

    def get_events(self, task_id: str, limit: int = 50) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM task_events WHERE task_id=? ORDER BY created_at DESC LIMIT ?",
                (task_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_human_help_tasks(self, limit: int = 100) -> List[Task]:
        """List tasks that are currently blocked and waiting for human input."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE status='needs_human' ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_task(r) for r in rows]

    def start_cycle(self) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO cycles (started_at, status) VALUES (?, 'running')",
                (_now_iso(),),
            )
            self._conn.commit()
            return cursor.lastrowid or 0

    def complete_cycle(
        self,
        cycle_id: int,
        tasks_discovered: int = 0,
        tasks_executed: int = 0,
        tasks_completed: int = 0,
        tasks_failed: int = 0,
        summary: str = "",
    ) -> None:
        with self._lock:
            self._conn.execute(
                """UPDATE cycles SET completed_at=?, tasks_discovered=?,
                   tasks_executed=?, tasks_completed=?, tasks_failed=?,
                   status='completed', summary=? WHERE id=?""",
                (_now_iso(), tasks_discovered, tasks_executed, tasks_completed, tasks_failed, summary, cycle_id),
            )
            self._conn.commit()

    def get_recent_cycles(self, limit: int = 20) -> List[CycleReport]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM cycles ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            CycleReport(
                cycle_id=r["id"],
                started_at=r["started_at"],
                completed_at=r["completed_at"] or "",
                tasks_discovered=r["tasks_discovered"],
                tasks_executed=r["tasks_executed"],
                tasks_completed=r["tasks_completed"],
                tasks_failed=r["tasks_failed"],
                status=r["status"],
                summary=r["summary"] or "",
            )
            for r in rows
        ]

    def get_stats(self) -> Dict:
        with self._lock:
            status_rows = self._conn.execute("SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status").fetchall()
            cycle_row = self._conn.execute("SELECT COUNT(*) as cnt FROM cycles").fetchone()
            token_row = self._conn.execute("SELECT COALESCE(SUM(token_cost), 0) as total FROM tasks").fetchone()
        counts: Dict[str, int] = {}
        for row in status_rows:
            counts[row["status"]] = row["cnt"]
        total = sum(counts.values())
        return {
            "total_tasks": total,
            "status_counts": counts,
            "total_cycles": cycle_row["cnt"] if cycle_row else 0,
            "total_tokens": token_row["total"] if token_row else 0,
        }

    def close(self) -> None:
        self._conn.close()

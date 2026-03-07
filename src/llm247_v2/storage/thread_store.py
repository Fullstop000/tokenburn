from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_SCHEMA = """
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
    role        TEXT NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_threads_status  ON threads(status);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_tt_task         ON thread_tasks(task_id);
"""

# Thread statuses
# open          - newly created by human (Shape B), waiting for agent to pick up
# waiting_reply - agent asked for help, waiting for human response
# replied       - human responded, agent hasn't processed yet
# closed        - interaction complete


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class Thread:
    id: str
    title: str
    status: str
    created_by: str
    created_at: str
    updated_at: str


@dataclass
class Message:
    id: str
    thread_id: str
    role: str
    body: str
    created_at: str


def _row_to_thread(row: sqlite3.Row) -> Thread:
    d = dict(row)
    return Thread(
        id=d["id"],
        title=d["title"],
        status=d["status"],
        created_by=d["created_by"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )


def _row_to_message(row: sqlite3.Row) -> Message:
    d = dict(row)
    return Message(
        id=d["id"],
        thread_id=d["thread_id"],
        role=d["role"],
        body=d["body"],
        created_at=d["created_at"],
    )


class ThreadStore:
    """SQLite store for human-agent interaction threads and messages."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── Thread CRUD ────────────────────────────────────────────────────────

    def create_thread(self, title: str, created_by: str, body: str = "") -> Thread:
        """Create a new thread with an optional opening message."""
        thread_id = _new_id()
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                """INSERT INTO threads (id, title, status, created_by, created_at, updated_at)
                   VALUES (?, ?, 'open', ?, ?, ?)""",
                (thread_id, title, created_by, now, now),
            )
            if body:
                self._conn.execute(
                    """INSERT INTO messages (id, thread_id, role, body, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (_new_id(), thread_id, created_by, body, now),
                )
            self._conn.commit()
            row = self._conn.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        return _row_to_thread(row)

    def get_thread(self, thread_id: str) -> Optional[Thread]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        return _row_to_thread(row) if row else None

    def list_threads(self, status: Optional[str] = None, limit: int = 100) -> list[Thread]:
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM threads WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM threads ORDER BY updated_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [_row_to_thread(r) for r in rows]

    def set_status(self, thread_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE threads SET status=?, updated_at=? WHERE id=?",
                (status, _now_iso(), thread_id),
            )
            self._conn.commit()

    # ── Messages ───────────────────────────────────────────────────────────

    def add_message(self, thread_id: str, role: str, body: str) -> Message:
        """Append one message and update thread timestamp."""
        msg_id = _new_id()
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                """INSERT INTO messages (id, thread_id, role, body, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (msg_id, thread_id, role, body, now),
            )
            self._conn.execute(
                "UPDATE threads SET updated_at=? WHERE id=?", (now, thread_id)
            )
            self._conn.commit()
            row = self._conn.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
        return _row_to_message(row)

    def get_messages(self, thread_id: str) -> list[Message]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE thread_id=? ORDER BY created_at ASC",
                (thread_id,),
            ).fetchall()
        return [_row_to_message(r) for r in rows]

    def count_agent_messages(self, thread_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE thread_id=? AND role='agent'",
                (thread_id,),
            ).fetchone()
        return row[0] if row else 0

    # ── Task linkage ───────────────────────────────────────────────────────

    def link_task(self, thread_id: str, task_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO thread_tasks (thread_id, task_id) VALUES (?, ?)",
                (thread_id, task_id),
            )
            self._conn.commit()

    def get_thread_for_task(self, task_id: str) -> Optional[Thread]:
        with self._lock:
            row = self._conn.execute(
                """SELECT t.* FROM threads t
                   JOIN thread_tasks tt ON tt.thread_id = t.id
                   WHERE tt.task_id=?
                   ORDER BY t.created_at DESC LIMIT 1""",
                (task_id,),
            ).fetchone()
        return _row_to_thread(row) if row else None

    def get_tasks_for_thread(self, thread_id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT task_id FROM thread_tasks WHERE thread_id=?", (thread_id,)
            ).fetchall()
        return [r["task_id"] for r in rows]

    def get_replied_threads(self) -> list[Thread]:
        return self.list_threads(status="replied")

    def close(self) -> None:
        self._conn.close()

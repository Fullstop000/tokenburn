from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from llm247_v2.storage.thread_store import ThreadStore


class TestThreadStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ThreadStore(Path(self.tmp.name) / "threads.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    # ── create_thread ──────────────────────────────────────────────────────

    def test_create_thread_defaults_to_open(self):
        thread = self.store.create_thread(title="Help needed", created_by="agent")
        self.assertEqual(thread.status, "open")
        self.assertEqual(thread.created_by, "agent")

    def test_create_thread_with_body_adds_message(self):
        thread = self.store.create_thread("Bug", created_by="human", body="Please fix this.")
        messages = self.store.get_messages(thread.id)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, "human")
        self.assertEqual(messages[0].body, "Please fix this.")

    def test_create_thread_without_body_has_no_messages(self):
        thread = self.store.create_thread("Silent", created_by="agent")
        self.assertEqual(len(self.store.get_messages(thread.id)), 0)

    # ── get / list ─────────────────────────────────────────────────────────

    def test_get_thread_returns_correct_thread(self):
        thread = self.store.create_thread("Test", created_by="agent")
        fetched = self.store.get_thread(thread.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.title, "Test")

    def test_get_thread_returns_none_for_missing(self):
        self.assertIsNone(self.store.get_thread("nonexistent"))

    def test_list_threads_all(self):
        self.store.create_thread("T1", created_by="agent")
        self.store.create_thread("T2", created_by="human")
        threads = self.store.list_threads()
        self.assertEqual(len(threads), 2)

    def test_list_threads_by_status(self):
        t1 = self.store.create_thread("T1", created_by="agent")
        self.store.create_thread("T2", created_by="human")
        self.store.set_status(t1.id, "waiting_reply")
        waiting = self.store.list_threads(status="waiting_reply")
        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0].id, t1.id)

    # ── messages ───────────────────────────────────────────────────────────

    def test_add_message_agent(self):
        thread = self.store.create_thread("T", created_by="agent")
        msg = self.store.add_message(thread.id, "agent", "Working on it.")
        self.assertEqual(msg.role, "agent")
        self.assertEqual(msg.body, "Working on it.")

    def test_add_message_updates_thread_timestamp(self):
        thread = self.store.create_thread("T", created_by="agent")
        ts_before = self.store.get_thread(thread.id).updated_at
        self.store.add_message(thread.id, "human", "Reply")
        ts_after = self.store.get_thread(thread.id).updated_at
        self.assertGreaterEqual(ts_after, ts_before)

    def test_get_messages_ordered_by_time(self):
        thread = self.store.create_thread("T", created_by="agent", body="First")
        self.store.add_message(thread.id, "human", "Second")
        self.store.add_message(thread.id, "agent", "Third")
        messages = self.store.get_messages(thread.id)
        self.assertEqual([m.body for m in messages], ["First", "Second", "Third"])

    def test_count_agent_messages(self):
        thread = self.store.create_thread("T", created_by="agent", body="Opening")
        self.store.add_message(thread.id, "agent", "Still blocked")
        self.store.add_message(thread.id, "human", "Here's info")
        self.assertEqual(self.store.count_agent_messages(thread.id), 2)

    # ── task linkage ───────────────────────────────────────────────────────

    def test_link_task_and_get_thread_for_task(self):
        thread = self.store.create_thread("T", created_by="agent")
        self.store.link_task(thread.id, "task-abc")
        found = self.store.get_thread_for_task("task-abc")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, thread.id)

    def test_get_thread_for_task_returns_none_when_unlinked(self):
        self.assertIsNone(self.store.get_thread_for_task("nonexistent"))

    def test_get_tasks_for_thread(self):
        thread = self.store.create_thread("T", created_by="agent")
        self.store.link_task(thread.id, "t1")
        self.store.link_task(thread.id, "t2")
        self.assertCountEqual(self.store.get_tasks_for_thread(thread.id), ["t1", "t2"])

    def test_link_task_is_idempotent(self):
        thread = self.store.create_thread("T", created_by="agent")
        self.store.link_task(thread.id, "t1")
        self.store.link_task(thread.id, "t1")
        self.assertEqual(len(self.store.get_tasks_for_thread(thread.id)), 1)

    # ── status ─────────────────────────────────────────────────────────────

    def test_set_status(self):
        thread = self.store.create_thread("T", created_by="agent")
        self.store.set_status(thread.id, "waiting_reply")
        updated = self.store.get_thread(thread.id)
        self.assertEqual(updated.status, "waiting_reply")

    def test_get_replied_threads(self):
        t1 = self.store.create_thread("T1", created_by="agent")
        t2 = self.store.create_thread("T2", created_by="agent")
        self.store.set_status(t1.id, "replied")
        replied = self.store.get_replied_threads()
        self.assertEqual(len(replied), 1)
        self.assertEqual(replied[0].id, t1.id)


if __name__ == "__main__":
    unittest.main()

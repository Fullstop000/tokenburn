import tempfile
import unittest
from pathlib import Path

from llm247_v2.core.models import Task, TaskStatus
from llm247_v2.storage.store import TaskStore


class TestTaskStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        self.store = TaskStore(self.db_path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _make_task(self, task_id="t1", title="Test Task", status="queued"):
        return Task(
            id=task_id, title=title, description="desc",
            source="manual", status=status, priority=2,
        )

    def test_insert_and_get(self):
        task = self._make_task()
        self.store.insert_task(task)
        loaded = self.store.get_task("t1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.title, "Test Task")

    def test_get_nonexistent(self):
        self.assertIsNone(self.store.get_task("missing"))

    def test_update(self):
        task = self._make_task()
        self.store.insert_task(task)
        task.status = TaskStatus.COMPLETED.value
        task.pr_url = "https://github.com/pr/1"
        self.store.update_task(task)
        loaded = self.store.get_task("t1")
        self.assertEqual(loaded.status, "completed")
        self.assertEqual(loaded.pr_url, "https://github.com/pr/1")

    def test_list_tasks(self):
        for i in range(5):
            self.store.insert_task(self._make_task(f"t{i}", f"Task {i}"))
        tasks = self.store.list_tasks()
        self.assertEqual(len(tasks), 5)

    def test_list_by_status(self):
        self.store.insert_task(self._make_task("t1", status="queued"))
        self.store.insert_task(self._make_task("t2", status="completed"))
        queued = self.store.list_tasks(status="queued")
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0].id, "t1")

    def test_get_next_queued(self):
        self.store.insert_task(self._make_task("t1", "Low Priority", status="queued"))
        t2 = self._make_task("t2", "High Priority", status="queued")
        t2.priority = 1
        self.store.insert_task(t2)
        nxt = self.store.get_next_queued_task()
        self.assertEqual(nxt.id, "t2")

    def test_has_duplicate(self):
        self.store.insert_task(self._make_task("t1", "Fix bug"))
        self.assertTrue(self.store.has_duplicate("Fix bug", "manual"))
        self.assertFalse(self.store.has_duplicate("New task", "manual"))

    def test_events(self):
        self.store.add_event("t1", "created", "from test")
        self.store.add_event("t1", "started", "")
        events = self.store.get_events("t1")
        self.assertEqual(len(events), 2)

    def test_cycles(self):
        cid = self.store.start_cycle()
        self.assertGreater(cid, 0)
        self.store.complete_cycle(cid, tasks_discovered=3, tasks_completed=1)
        cycles = self.store.get_recent_cycles()
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0].tasks_discovered, 3)

    def test_stats(self):
        self.store.insert_task(self._make_task("t1", status="queued"))
        self.store.insert_task(self._make_task("t2", status="completed"))
        stats = self.store.get_stats()
        self.assertEqual(stats["total_tasks"], 2)
        self.assertEqual(stats["status_counts"]["queued"], 1)
        self.assertEqual(stats["status_counts"]["completed"], 1)

    def test_insert_ignore_duplicate_id(self):
        self.store.insert_task(self._make_task("t1", "First"))
        self.store.insert_task(self._make_task("t1", "Second"))
        loaded = self.store.get_task("t1")
        self.assertEqual(loaded.title, "First")


if __name__ == "__main__":
    unittest.main()

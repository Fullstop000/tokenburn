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

    def test_get_next_executable_prioritizes_human_resolved(self):
        queued = self._make_task("t-queued", "Queued task", status=TaskStatus.QUEUED.value)
        queued.priority = 1
        human_resolved = self._make_task("t-resolved", "Resolved by human", status=TaskStatus.HUMAN_RESOLVED.value)
        human_resolved.priority = 5

        self.store.insert_task(queued)
        self.store.insert_task(human_resolved)

        nxt = self.store.get_next_executable_task()
        self.assertEqual(nxt.id, "t-resolved")

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
        queued = self._make_task("t1", status="queued")
        queued.prompt_token_cost = 30
        queued.completion_token_cost = 10
        queued.token_cost = 40
        completed = self._make_task("t2", status="completed")
        completed.prompt_token_cost = 70
        completed.completion_token_cost = 20
        completed.token_cost = 90
        self.store.insert_task(queued)
        self.store.insert_task(completed)
        stats = self.store.get_stats()
        self.assertEqual(stats["total_tasks"], 2)
        self.assertEqual(stats["status_counts"]["queued"], 1)
        self.assertEqual(stats["status_counts"]["completed"], 1)
        self.assertEqual(stats["input_tokens"], 100)
        self.assertEqual(stats["output_tokens"], 30)
        self.assertEqual(stats["total_tokens"], 130)

    def test_insert_ignore_duplicate_id(self):
        self.store.insert_task(self._make_task("t1", "First"))
        self.store.insert_task(self._make_task("t1", "Second"))
        loaded = self.store.get_task("t1")
        self.assertEqual(loaded.title, "First")

    def test_human_help_request_persistence(self):
        task = self._make_task("t-human", "Needs help", status=TaskStatus.NEEDS_HUMAN.value)
        task.human_help_request = "Please configure external API key in environment."
        self.store.insert_task(task)

        loaded = self.store.get_task("t-human")
        self.assertEqual(loaded.status, TaskStatus.NEEDS_HUMAN.value)
        self.assertEqual(loaded.human_help_request, "Please configure external API key in environment.")

    def test_list_human_help_tasks(self):
        needs_help = self._make_task("t-help", "Blocked by human", status=TaskStatus.NEEDS_HUMAN.value)
        needs_help.human_help_request = "Please resolve merge conflict in branch."
        self.store.insert_task(needs_help)
        self.store.insert_task(self._make_task("t-ok", "Normal queue", status=TaskStatus.QUEUED.value))

        tasks = self.store.list_human_help_tasks(limit=20)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, "t-help")


if __name__ == "__main__":
    unittest.main()

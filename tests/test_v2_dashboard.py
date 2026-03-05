import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from llm247_v2.dashboard import serve_dashboard, _api_tasks, _api_stats, _api_inject_task, _api_task_detail, _task_row, _task_full
from llm247_v2.directive import save_directive
from llm247_v2.models import Directive, Task
from llm247_v2.store import TaskStore


class TestDashboardAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        self.store = TaskStore(self.db_path)
        self.directive_path = Path(self.tmp.name) / "directive.json"
        save_directive(self.directive_path, Directive())

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_api_tasks_empty(self):
        result = _api_tasks(self.store)
        self.assertIn("tasks", result)
        self.assertEqual(len(result["tasks"]), 0)

    def test_api_tasks_with_data(self):
        self.store.insert_task(Task(
            id="t1", title="Test", description="D", source="manual",
            status="queued", priority=2,
        ))
        result = _api_tasks(self.store)
        self.assertEqual(len(result["tasks"]), 1)
        self.assertEqual(result["tasks"][0]["title"], "Test")

    def test_api_stats(self):
        self.store.insert_task(Task(
            id="t1", title="T", description="D", source="manual",
            status="completed", priority=2,
        ))
        stats = _api_stats(self.store)
        self.assertEqual(stats["total_tasks"], 1)
        self.assertIn("completed", stats["status_counts"])

    def test_inject_task(self):
        result = _api_inject_task(self.store, {"title": "Manual task", "priority": 1})
        self.assertEqual(result["status"], "ok")
        tasks = self.store.list_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].title, "Manual task")

    def test_inject_no_title(self):
        result = _api_inject_task(self.store, {})
        self.assertIn("error", result)


class TestTaskDetailAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        self.store = TaskStore(self.db_path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_task_detail_returns_full_data(self):
        long_plan = '{"steps": [' + ', '.join(['{"action": "edit"}'] * 50) + ']}'
        long_log = "step result\n" * 200
        self.store.insert_task(Task(
            id="full1", title="Full Detail Task", description="desc",
            source="manual", status="completed", priority=2,
            plan=long_plan, execution_log=long_log,
            token_cost=12345, time_cost_seconds=67.8,
            whats_learned="[pattern] Always validate input\n[pitfall] Don't skip tests",
        ))
        result = _api_task_detail(self.store, "full1")
        t = result["task"]
        self.assertEqual(t["plan"], long_plan)
        self.assertEqual(t["execution_log"], long_log)
        self.assertEqual(t["token_cost"], 12345)
        self.assertEqual(t["time_cost_seconds"], 67.8)
        self.assertIn("Always validate input", t["whats_learned"])
        self.assertIn("cycle_id", t)

    def test_task_detail_not_found(self):
        result = _api_task_detail(self.store, "nonexistent")
        self.assertIn("error", result)

    def test_task_row_truncates(self):
        long_plan = "x" * 2000
        long_log = "y" * 2000
        t = Task(
            id="t1", title="T", description="D", source="s",
            status="queued", priority=2,
            plan=long_plan, execution_log=long_log,
            token_cost=999, time_cost_seconds=12.5,
            whats_learned="z" * 500,
        )
        row = _task_row(t)
        self.assertEqual(len(row["plan"]), 500)
        self.assertEqual(len(row["execution_log"]), 500)
        self.assertEqual(len(row["whats_learned"]), 200)
        self.assertEqual(row["token_cost"], 999)
        self.assertEqual(row["time_cost_seconds"], 12.5)

    def test_task_full_no_truncation(self):
        long_plan = "x" * 2000
        t = Task(
            id="t1", title="T", description="D", source="s",
            status="queued", priority=2,
            plan=long_plan, token_cost=1000, time_cost_seconds=5.0,
            whats_learned="learned stuff",
        )
        full = _task_full(t)
        self.assertEqual(len(full["plan"]), 2000)
        self.assertEqual(full["token_cost"], 1000)
        self.assertEqual(full["whats_learned"], "learned stuff")

    def test_task_detail_includes_events(self):
        self.store.insert_task(Task(
            id="ev1", title="Event Task", description="d",
            source="manual", status="queued", priority=2,
        ))
        self.store.add_event("ev1", "plan.started", "Planning began")
        self.store.add_event("ev1", "execute.step", "Edited file")
        result = _api_task_detail(self.store, "ev1")
        self.assertEqual(len(result["events"]), 2)


class TestDashboardServer(unittest.TestCase):
    def test_server_starts_and_serves(self):
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "test.db"
        store = TaskStore(db_path)
        directive_path = Path(tmp.name) / "directive.json"
        save_directive(directive_path, Directive())

        port = 18787

        def run_server():
            serve_dashboard(store, directive_path, host="127.0.0.1", port=port)

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        time.sleep(0.5)

        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
            html = resp.read().decode()
            self.assertIn("TokenBurn Agent V2", html)

            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/tasks")
            data = json.loads(resp.read().decode())
            self.assertIn("tasks", data)

            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/stats")
            data = json.loads(resp.read().decode())
            self.assertIn("total_tasks", data)
        finally:
            store.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

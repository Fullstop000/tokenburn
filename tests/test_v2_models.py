import unittest

from llm247_v2.models import (
    CycleReport,
    Directive,
    PlanStep,
    Task,
    TaskPlan,
    TaskSource,
    TaskSourceConfig,
    TaskStatus,
)


class TestTaskStatus(unittest.TestCase):
    def test_enum_values(self):
        self.assertEqual(TaskStatus.DISCOVERED.value, "discovered")
        self.assertEqual(TaskStatus.COMPLETED.value, "completed")
        self.assertEqual(TaskStatus.FAILED.value, "failed")

    def test_all_statuses_are_strings(self):
        for status in TaskStatus:
            self.assertIsInstance(status.value, str)


class TestTaskSource(unittest.TestCase):
    def test_sources(self):
        self.assertEqual(TaskSource.TODO_SCAN.value, "todo_scan")
        self.assertEqual(TaskSource.MANUAL.value, "manual")


class TestTask(unittest.TestCase):
    def test_defaults(self):
        task = Task(id="abc", title="Fix bug", description="Details", source="manual")
        self.assertEqual(task.status, "discovered")
        self.assertEqual(task.priority, 3)
        self.assertEqual(task.branch_name, "")

    def test_all_fields(self):
        task = Task(
            id="t1", title="T", description="D", source="todo_scan",
            status="executing", priority=1, branch_name="agent/t1-fix",
            pr_url="https://github.com/pr/1",
        )
        self.assertEqual(task.pr_url, "https://github.com/pr/1")


class TestDirective(unittest.TestCase):
    def test_defaults(self):
        d = Directive()
        self.assertFalse(d.paused)
        self.assertEqual(d.focus_areas, [])
        self.assertEqual(d.poll_interval_seconds, 120)

    def test_task_source_config(self):
        cfg = TaskSourceConfig(enabled=False, priority=5)
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.priority, 5)


class TestTaskPlan(unittest.TestCase):
    def test_plan_with_steps(self):
        plan = TaskPlan(
            task_id="t1",
            steps=[PlanStep(action="edit_file", target="foo.py", content="x=1")],
            commit_message="fix: update foo",
        )
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].action, "edit_file")


class TestCycleReport(unittest.TestCase):
    def test_defaults(self):
        r = CycleReport(cycle_id=1, started_at="2025-01-01T00:00:00Z")
        self.assertEqual(r.status, "running")
        self.assertEqual(r.tasks_discovered, 0)


if __name__ == "__main__":
    unittest.main()

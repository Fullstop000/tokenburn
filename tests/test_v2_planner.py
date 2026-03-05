import unittest

from llm247_v2.models import Directive, Task
from llm247_v2.planner import deserialize_plan, serialize_plan
from llm247_v2.models import PlanStep, TaskPlan


class FakeLLM:
    def __init__(self, response: str = ""):
        self.response = response
        self.calls = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response


class TestPlanSerialization(unittest.TestCase):
    def test_round_trip(self):
        plan = TaskPlan(
            task_id="t1",
            steps=[
                PlanStep(action="edit_file", target="foo.py", content="x=1", description="set x"),
                PlanStep(action="run_command", target="pytest", description="run tests"),
            ],
            commit_message="fix: update foo",
            pr_title="Fix foo",
            pr_body="Changed x to 1",
        )
        raw = serialize_plan(plan)
        loaded = deserialize_plan(raw)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.task_id, "t1")
        self.assertEqual(len(loaded.steps), 2)
        self.assertEqual(loaded.steps[0].action, "edit_file")
        self.assertEqual(loaded.commit_message, "fix: update foo")

    def test_deserialize_invalid(self):
        self.assertIsNone(deserialize_plan("not json"))
        self.assertIsNone(deserialize_plan(""))


class TestPlanTask(unittest.TestCase):
    def test_valid_llm_response(self):
        from llm247_v2.planner import plan_task
        from pathlib import Path
        import tempfile

        llm = FakeLLM('{"steps": [{"action": "edit_file", "target": "x.py", "content": "pass", "description": "fix"}], '
                       '"commit_message": "fix: x", "pr_title": "Fix X", "pr_body": "Fixed X"}')
        task = Task(id="t1", title="Fix X", description="Fix x.py", source="manual")
        directive = Directive()

        with tempfile.TemporaryDirectory() as tmp:
            plan = plan_task(task, Path(tmp), directive, llm)
            self.assertEqual(len(plan.steps), 1)
            self.assertEqual(plan.commit_message, "fix: x")

    def test_fallback_on_bad_response(self):
        from llm247_v2.planner import plan_task
        from pathlib import Path
        import tempfile

        llm = FakeLLM("not a json response at all")
        task = Task(id="t1", title="Fix X", description="Fix x.py", source="manual")
        directive = Directive()

        with tempfile.TemporaryDirectory() as tmp:
            plan = plan_task(task, Path(tmp), directive, llm)
            self.assertEqual(len(plan.steps), 0)
            self.assertEqual(plan.pr_title, "Fix X")


if __name__ == "__main__":
    unittest.main()

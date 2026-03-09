import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from llm247_v2.agent import AutonomousAgentV2, run_agent_loop
from llm247_v2.core.directive import save_directive
from llm247_v2.llm.client import BudgetExhaustedError
from llm247_v2.core.models import Directive, ModelBindingPoint, Task, TaskSourceConfig, TaskStatus
from llm247_v2.observability.observer import MemoryHandler, Observer
from llm247_v2.storage.store import TaskStore


class FakeLLM:
    def __init__(self):
        self.call_count = 0

    def generate(self, prompt: str) -> str:
        self.call_count += 1
        return '{"tasks": [{"title": "Improve test coverage", "description": "Add tests", "priority": 2}]}'

    def generate_with_tools(self, messages, tools):
        from llm247_v2.core.models import ToolCall
        from llm247_v2.llm.client import UsageInfo
        return None, [ToolCall(tool="finish", arguments={"summary": "done"})], UsageInfo()


class FakeRouter:
    """LLM client that routes to different sub-clients by binding point."""

    def __init__(self, mapping, default_response="default"):
        self.mapping = mapping
        self.default_response = default_response
        self.points: list[str] = []

    def for_point(self, point: str):
        self.points.append(point)
        return self.mapping.get(point, _FakeDefaultLLM(self.default_response))

    def generate(self, prompt: str) -> str:
        return self.default_response

    def generate_with_tools(self, messages, tools):
        from llm247_v2.core.models import ToolCall
        from llm247_v2.llm.client import UsageInfo
        return None, [ToolCall(tool="finish", arguments={"summary": "done"})], UsageInfo()


class _FakeDefaultLLM:
    def __init__(self, response):
        self._response = response

    def generate(self, prompt: str) -> str:
        return self._response

    def generate_with_tools(self, messages, tools):
        from llm247_v2.core.models import ToolCall
        from llm247_v2.llm.client import UsageInfo
        return None, [ToolCall(tool="finish", arguments={"summary": "done"})], UsageInfo()


class TestAutonomousAgentV2(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        (self.workspace / "src").mkdir()
        (self.workspace / "tests").mkdir()
        (self.workspace / "src" / "example.py").write_text("x = 1\n", encoding="utf-8")

        self.state_dir = self.workspace / ".llm247_v2"
        self.db_path = self.state_dir / "tasks.db"
        self.directive_path = self.state_dir / "directive.json"
        self.constitution_path = self.state_dir / "constitution.md"
        self.exploration_map_path = self.state_dir / "exploration_map.json"

        self.store = TaskStore(self.db_path)
        self.llm = FakeLLM()

        directive = Directive(
            task_sources={
                "todo_scan": TaskSourceConfig(enabled=False),
                "test_gap": TaskSourceConfig(enabled=True, priority=2),
                "lint_check": TaskSourceConfig(enabled=False),
                "self_improvement": TaskSourceConfig(enabled=False),
            }
        )
        save_directive(self.directive_path, directive)

        self.memory_handler = MemoryHandler()
        self.observer = Observer(handlers=[self.memory_handler])

        self.agent = AutonomousAgentV2(
            workspace=self.workspace,
            store=self.store,
            llm=self.llm,
            directive_path=self.directive_path,
            constitution_path=self.constitution_path,
            exploration_map_path=self.exploration_map_path,
            observer=self.observer,
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_paused_directive_skips_cycle(self):
        directive = Directive(paused=True)
        save_directive(self.directive_path, directive)
        result = self.agent.run_cycle()
        self.assertEqual(result["status"], "paused")
        paused_events = self.memory_handler.find(module="Cycle", family="lifecycle", event_name="cycle_paused")
        self.assertEqual(len(paused_events), 1)

    def test_discovery_phase_creates_tasks(self):
        result = self.agent.run_cycle()
        self.assertGreaterEqual(result["tasks_discovered"], 0)
        cycles = self.store.get_recent_cycles()
        self.assertEqual(len(cycles), 1)

    def test_cycle_creates_cycle_record(self):
        self.agent.run_cycle()
        cycles = self.store.get_recent_cycles()
        self.assertGreater(len(cycles), 0)
        self.assertEqual(cycles[0].status, "completed")

    def test_observer_receives_cycle_events(self):
        self.agent.run_cycle()
        starts = self.memory_handler.find(module="Cycle", family="lifecycle", event_name="cycle_started")
        ends = self.memory_handler.find(module="Cycle", family="lifecycle", event_name="cycle_completed")
        self.assertEqual(len(starts), 1)
        self.assertEqual(len(ends), 1)

    def test_execution_success_completes_task(self):
        task = Task(
            id="exec-success-1",
            title="Task that succeeds",
            description="manual test",
            source="manual",
            status=TaskStatus.QUEUED.value,
            priority=1,
        )
        self.store.insert_task(task)
        directive = Directive()
        from llm247_v2.core.constitution import load_constitution
        constitution = load_constitution(self.constitution_path)

        with patch("llm247_v2.execution.loop.ReActLoop.run", return_value=(True, [], "")):
            success = self.agent._execute_single_task(task, directive, constitution)

        self.assertTrue(success)
        updated = self.store.get_task(task.id)
        self.assertEqual(updated.status, TaskStatus.COMPLETED.value)

    def test_execution_failure_sets_needs_human(self):
        task = Task(
            id="exec-fail-1",
            title="Task that fails",
            description="manual test",
            source="manual",
            status=TaskStatus.QUEUED.value,
            priority=1,
        )
        self.store.insert_task(task)
        directive = Directive()
        from llm247_v2.core.constitution import load_constitution
        constitution = load_constitution(self.constitution_path)

        with patch("llm247_v2.execution.loop.ReActLoop.run", return_value=(False, [], "mock failure")):
            success = self.agent._execute_single_task(task, directive, constitution)

        self.assertFalse(success)
        updated = self.store.get_task(task.id)
        self.assertEqual(updated.status, TaskStatus.NEEDS_HUMAN.value)
        self.assertTrue(updated.human_help_request)

    def test_execution_uses_execution_binding_point(self):
        task = Task(
            id="exec-route-1",
            title="Route execution model",
            description="manual test",
            source="manual",
            status=TaskStatus.QUEUED.value,
            priority=1,
        )
        self.store.insert_task(task)
        execution_llm = FakeLLM()
        self.agent.llm = FakeRouter({ModelBindingPoint.EXECUTION.value: execution_llm})
        directive = Directive()
        from llm247_v2.core.constitution import load_constitution
        constitution = load_constitution(self.constitution_path)

        captured = {}

        def capture_run(self_loop, task, workspace, directive, experience_context=""):
            captured["llm"] = self_loop.llm
            return True, [], ""

        with patch("llm247_v2.execution.loop.ReActLoop.run", capture_run):
            self.agent._execute_single_task(task, directive, constitution)

        self.assertIn(ModelBindingPoint.EXECUTION.value, self.agent.llm.points)

    def test_learning_extraction_uses_learning_binding_point(self):
        task = Task(
            id="learning-route",
            title="Route learning model",
            description="manual test",
            source="manual",
            status=TaskStatus.COMPLETED.value,
            priority=1,
            execution_log="done",
        )
        learning_llm = FakeLLM()
        learning_llm.generate = lambda prompt: '{"learnings": []}'
        self.agent.llm = FakeRouter({ModelBindingPoint.LEARNING_EXTRACTION.value: learning_llm})
        self.agent.exp_store = MagicMock()

        captured = {}

        def capture_extract(**kwargs):
            captured["response"] = kwargs["llm_generate"]("prompt")
            return []

        with patch("llm247_v2.agent.extract_learnings", side_effect=capture_extract):
            self.agent._extract_and_store_learnings(task, "completed")

        self.assertEqual(captured["response"], '{"learnings": []}')
        self.assertIn(ModelBindingPoint.LEARNING_EXTRACTION.value, self.agent.llm.points)


class TestRunAgentLoop(unittest.TestCase):
    def _make_agent_mock(self, **overrides):
        agent = MagicMock()
        agent.shutdown_requested = False
        for k, v in overrides.items():
            setattr(agent, k, v)
        return agent

    def test_max_cycles(self):
        agent = self._make_agent_mock()
        agent.run_cycle.return_value = {"status": "ok"}
        noop = lambda _: None
        reason = run_agent_loop(agent, poll_interval=0, max_cycles=2, sleeper=noop)
        self.assertEqual(reason, "max_cycles_reached")
        self.assertEqual(agent.run_cycle.call_count, 2)

    def test_budget_exhausted(self):
        agent = self._make_agent_mock()
        agent.run_cycle.side_effect = BudgetExhaustedError("quota exceeded")
        noop = lambda _: None
        reason = run_agent_loop(agent, poll_interval=0, max_cycles=10, sleeper=noop)
        self.assertEqual(reason, "budget_exhausted")

    def test_shutdown_event_stops_loop(self):
        agent = self._make_agent_mock(shutdown_requested=True)
        noop = lambda _: None
        reason = run_agent_loop(agent, poll_interval=0, max_cycles=10, sleeper=noop)
        self.assertEqual(reason, "interrupted")
        agent.run_cycle.assert_not_called()


if __name__ == "__main__":
    unittest.main()

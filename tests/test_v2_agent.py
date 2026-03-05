import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from llm247_v2.agent import AutonomousAgentV2, run_agent_loop
from llm247_v2.directive import save_directive
from llm247_v2.llm_client import BudgetExhaustedError
from llm247_v2.models import Directive, TaskSourceConfig
from llm247_v2.observer import MemoryHandler, Observer
from llm247_v2.store import TaskStore


class FakeLLM:
    def __init__(self):
        self.call_count = 0

    def generate(self, prompt: str) -> str:
        self.call_count += 1
        return '{"tasks": [{"title": "Improve test coverage", "description": "Add tests", "priority": 2}]}'


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
        paused_events = self.memory_handler.find(phase="cycle", action="paused")
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
        starts = self.memory_handler.find(phase="cycle", action="started")
        ends = self.memory_handler.find(phase="cycle", action="completed")
        self.assertEqual(len(starts), 1)
        self.assertEqual(len(ends), 1)


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

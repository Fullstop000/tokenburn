import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from llm247_v2.observability.observer import (
    AgentEvent,
    ConsoleHandler,
    HumanLogHandler,
    JsonLogHandler,
    MemoryHandler,
    NullObserver,
    Observer,
    StoreHandler,
    _short_time,
)


class TestAgentEvent(unittest.TestCase):
    def test_creation(self):
        e = AgentEvent(phase="cycle", action="started", detail="Cycle #1")
        self.assertEqual(e.phase, "cycle")
        self.assertEqual(e.action, "started")
        self.assertIn("Cycle #1", e.detail)
        self.assertTrue(e.timestamp)

    def test_frozen(self):
        e = AgentEvent(phase="cycle", action="started")
        with self.assertRaises(AttributeError):
            e.phase = "execute"

    def test_defaults(self):
        e = AgentEvent(phase="x", action="y")
        self.assertEqual(e.task_id, "")
        self.assertEqual(e.cycle_id, 0)
        self.assertIsNone(e.success)
        self.assertEqual(e.reasoning, "")
        self.assertEqual(e.metadata, {})


class TestMemoryHandler(unittest.TestCase):
    def test_collects_events(self):
        h = MemoryHandler()
        h.handle(AgentEvent(phase="cycle", action="started"))
        h.handle(AgentEvent(phase="execute", action="step [1/3]"))
        h.handle(AgentEvent(phase="cycle", action="completed"))
        self.assertEqual(len(h.events), 3)

    def test_find_by_phase(self):
        h = MemoryHandler()
        h.handle(AgentEvent(phase="cycle", action="started"))
        h.handle(AgentEvent(phase="execute", action="step"))
        h.handle(AgentEvent(phase="cycle", action="completed"))
        self.assertEqual(len(h.find(phase="cycle")), 2)
        self.assertEqual(len(h.find(phase="execute")), 1)

    def test_find_by_action(self):
        h = MemoryHandler()
        h.handle(AgentEvent(phase="cycle", action="started"))
        h.handle(AgentEvent(phase="cycle", action="completed"))
        self.assertEqual(len(h.find(action="started")), 1)

    def test_find_by_both(self):
        h = MemoryHandler()
        h.handle(AgentEvent(phase="cycle", action="started"))
        h.handle(AgentEvent(phase="execute", action="started"))
        self.assertEqual(len(h.find(phase="cycle", action="started")), 1)


class TestHumanLogHandler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmp.name) / "activity.log"

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_to_file(self):
        h = HumanLogHandler(self.log_path)
        h.handle(AgentEvent(phase="cycle", action="started", detail="Cycle #42"))
        h.flush()
        content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("CYCLE", content)
        self.assertIn("started", content)
        self.assertIn("Cycle #42", content)
        h.close()

    def test_includes_task_id(self):
        h = HumanLogHandler(self.log_path)
        h.handle(AgentEvent(phase="execute", action="step [1/3]", task_id="abc12345def", detail="edit_file x.py"))
        h.flush()
        content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("[abc12345]", content)
        h.close()

    def test_includes_success_icon(self):
        h = HumanLogHandler(self.log_path)
        h.handle(AgentEvent(phase="verify", action="completed", success=True, detail="all passed"))
        h.handle(AgentEvent(phase="verify", action="completed", success=False, detail="syntax error"))
        h.flush()
        content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("✓", content)
        self.assertIn("✗", content)
        h.close()

    def test_separator_line(self):
        h = HumanLogHandler(self.log_path)
        h.handle(AgentEvent(phase="cycle", action="separator"))
        h.flush()
        content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("━", content)
        h.close()

    def test_includes_reasoning(self):
        h = HumanLogHandler(self.log_path)
        h.handle(AgentEvent(phase="decision", action="made", detail="skip discovery", reasoning="queue is full"))
        h.flush()
        content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("reason:", content)
        self.assertIn("queue is full", content)
        h.close()


class TestJsonLogHandler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmp.name) / "activity.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_valid_jsonl(self):
        h = JsonLogHandler(self.log_path)
        h.handle(AgentEvent(phase="cycle", action="started", cycle_id=42))
        h.handle(AgentEvent(phase="execute", action="step", task_id="t1", success=True))
        h.flush()

        lines = self.log_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            data = json.loads(line)
            self.assertIn("phase", data)
            self.assertIn("action", data)
        h.close()

    def test_omits_empty_fields(self):
        h = JsonLogHandler(self.log_path)
        h.handle(AgentEvent(phase="cycle", action="started"))
        h.flush()
        data = json.loads(self.log_path.read_text(encoding="utf-8").strip())
        self.assertNotIn("task_id", data)
        self.assertNotIn("reasoning", data)
        h.close()


class TestStoreHandler(unittest.TestCase):
    def test_persists_to_store(self):
        store = MagicMock()
        h = StoreHandler(store)
        h.handle(AgentEvent(phase="execute", action="step", task_id="t1", detail="edit x.py", success=True))
        store.add_event.assert_called_once()
        call_args = store.add_event.call_args
        self.assertEqual(call_args[0][0], "t1")
        self.assertIn("execute.step", call_args[0][1])
        self.assertIn("edit x.py", call_args[0][2])

    def test_skips_events_without_task_id(self):
        store = MagicMock()
        h = StoreHandler(store)
        h.handle(AgentEvent(phase="cycle", action="started"))
        store.add_event.assert_not_called()


class TestObserver(unittest.TestCase):
    def test_dispatches_to_all_handlers(self):
        h1 = MemoryHandler()
        h2 = MemoryHandler()
        obs = Observer(handlers=[h1, h2])
        obs.emit(AgentEvent(phase="cycle", action="started"))
        self.assertEqual(len(h1.events), 1)
        self.assertEqual(len(h2.events), 1)

    def test_handler_failure_does_not_stop_others(self):
        broken = MagicMock()
        broken.handle.side_effect = RuntimeError("boom")
        good = MemoryHandler()
        obs = Observer(handlers=[broken, good])
        obs.emit(AgentEvent(phase="cycle", action="started"))
        self.assertEqual(len(good.events), 1)

    def test_convenience_cycle_start(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.cycle_start(42)
        self.assertEqual(len(h.events), 2)
        self.assertEqual(h.events[0].action, "separator")
        self.assertEqual(h.events[1].action, "started")
        self.assertEqual(h.events[1].cycle_id, 42)

    def test_convenience_cycle_end(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.cycle_end(42, discovered=3, executed=1, completed=1, failed=0)
        self.assertEqual(len(h.events), 1)
        self.assertTrue(h.events[0].success)
        self.assertIn("+3 discovered", h.events[0].detail)

    def test_convenience_task_flow(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.plan_started("t1", "Fix bug")
        obs.plan_created("t1", 3, "fix(parser): handle edge case")
        obs.execute_step("t1", 0, 3, "edit_file", "src/x.py", True)
        obs.execute_step("t1", 1, 3, "create_file", "tests/t.py", True)
        obs.execute_step("t1", 2, 3, "run_command", "pytest", False, output="1 failed")
        obs.execute_finished("t1", False)
        obs.task_failed("t1", "test failure")

        self.assertEqual(len(h.events), 7)
        fail_events = h.find(action="task_failed")
        self.assertEqual(len(fail_events), 1)
        self.assertFalse(fail_events[0].success)

    def test_convenience_git_flow(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.git_worktree("t1", "agent/fix-bug", success=True)
        obs.git_committed("t1", "fix(parser): handle empty input")
        obs.git_pushed("t1")
        obs.git_pr("t1", "https://github.com/org/repo/pull/42", success=True)

        self.assertEqual(len(h.events), 4)
        pr = h.find(phase="git", action="pr_created")
        self.assertEqual(len(pr), 1)
        self.assertTrue(pr[0].success)

    def test_decision_event(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.decision("Skip stale area", reasoning="Recently explored 2h ago")
        self.assertEqual(len(h.events), 1)
        self.assertEqual(h.events[0].phase, "decision")
        self.assertIn("Recently explored", h.events[0].reasoning)

    def test_value_assessed(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.value_assessed("t1", "Fix bug in parser", 0.82, "execute")
        obs.value_assessed("t2", "Rename variable", 0.25, "skip")
        self.assertEqual(len(h.events), 2)
        self.assertTrue(h.events[0].success)
        self.assertFalse(h.events[1].success)


class TestDiscoveryObserverMethods(unittest.TestCase):
    def test_discover_raw_candidates(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.discover_raw_candidates([
            {"id": "t1", "title": "Fix parser bug", "source": "todo_scan"},
            {"id": "t2", "title": "Add tests", "source": "test_gap"},
        ])
        found = h.find(phase="discover", action="candidate_found")
        self.assertEqual(len(found), 2)
        self.assertIn("Fix parser bug", found[0].detail)
        self.assertIn("Add tests", found[1].detail)

    def test_discover_value_scored(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.discover_value_scored("t1", "Fix parser bug", 0.82, "execute", "impact=0.9, scope=0.7")
        scored = h.find(phase="value", action="scored")
        self.assertEqual(len(scored), 1)
        self.assertIn("0.820", scored[0].detail)
        self.assertTrue(scored[0].success)
        self.assertIn("impact=0.9", scored[0].reasoning)

    def test_discover_value_scored_skip(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.discover_value_scored("t1", "Low value task", 0.15, "skip", "impact=0.1")
        scored = h.find(phase="value", action="scored")
        self.assertFalse(scored[0].success)

    def test_discover_filtered_out(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.discover_filtered_out("t1", "Rename variable", 0.15, "heuristic score too low")
        filtered = h.find(phase="value", action="filtered_out")
        self.assertEqual(len(filtered), 1)
        self.assertFalse(filtered[0].success)
        self.assertIn("heuristic", filtered[0].reasoning)

    def test_discover_summary(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.discover_summary(raw=10, after_heuristic=6, after_llm=3, final=3)
        funnel = h.find(phase="discover", action="funnel")
        self.assertEqual(len(funnel), 1)
        self.assertIn("raw=10", funnel[0].detail)
        self.assertIn("final=3", funnel[0].detail)

    def test_experience_injected(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.experience_injected("t1", 3, "pattern A; pitfall B; insight C")
        injected = h.find(phase="plan", action="experience_injected")
        self.assertEqual(len(injected), 1)
        self.assertIn("3 experiences", injected[0].detail)
        self.assertIn("pattern A", injected[0].reasoning)


class TestNullObserver(unittest.TestCase):
    def test_no_crash(self):
        obs = NullObserver()
        obs.cycle_start(1)
        obs.cycle_end(1, 0, 0, 0, 0)
        obs.emit(AgentEvent(phase="x", action="y"))


class TestShortTime(unittest.TestCase):
    def test_valid_iso(self):
        result = _short_time("2026-03-05T14:30:22+00:00")
        self.assertEqual(result, "14:30:22")

    def test_invalid_falls_back(self):
        result = _short_time("garbage")
        self.assertRegex(result, r"\d{2}:\d{2}:\d{2}")


if __name__ == "__main__":
    unittest.main()

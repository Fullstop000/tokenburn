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
        e = AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started", detail="Cycle #1")
        self.assertEqual(e.module, "Cycle")
        self.assertEqual(e.family, "lifecycle")
        self.assertEqual(e.event_name, "cycle_started")
        self.assertIn("Cycle #1", e.detail)
        self.assertTrue(e.timestamp)
        self.assertTrue(e.event_id)

    def test_creation_with_new_envelope_fields(self):
        e = AgentEvent(
            module="Execution",
            family="tool_call",
            event_name="tool_call_succeeded",
            task_id="task-123",
            thread_id="thread-1",
            llm_seq=7,
            detail="read_file src/app.py",
            data={
                "step_id": "step-1",
                "tool_call_id": "call-1",
                "tool_type": "filesystem",
                "tool_name": "read_file",
            },
        )
        self.assertEqual(e.module, "Execution")
        self.assertEqual(e.family, "tool_call")
        self.assertEqual(e.event_name, "tool_call_succeeded")
        self.assertEqual(e.thread_id, "thread-1")
        self.assertEqual(e.llm_seq, 7)
        self.assertEqual(e.data["tool_name"], "read_file")

    def test_frozen(self):
        e = AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started")
        with self.assertRaises(AttributeError):
            e.module = "Execution"

    def test_defaults(self):
        e = AgentEvent(module="X", family="general", event_name="y")
        self.assertEqual(e.task_id, "")
        self.assertEqual(e.cycle_id, 0)
        self.assertEqual(e.thread_id, "")
        self.assertEqual(e.llm_seq, 0)
        self.assertIsNone(e.success)
        self.assertEqual(e.reasoning, "")
        self.assertEqual(e.data, {})
        self.assertEqual(e.module, "X")
        self.assertEqual(e.family, "general")
        self.assertEqual(e.event_name, "y")
        self.assertTrue(e.event_id)


class TestMemoryHandler(unittest.TestCase):
    def test_collects_events(self):
        h = MemoryHandler()
        h.handle(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started"))
        h.handle(AgentEvent(module="Execution", family="tool_call", event_name="tool_call_succeeded"))
        h.handle(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_completed"))
        self.assertEqual(len(h.events), 3)

    def test_find_by_module(self):
        h = MemoryHandler()
        h.handle(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started"))
        h.handle(AgentEvent(module="Execution", family="tool_call", event_name="tool_call_succeeded"))
        h.handle(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_completed"))
        self.assertEqual(len(h.find(module="Cycle")), 2)
        self.assertEqual(len(h.find(module="Execution")), 1)

    def test_find_by_event_name(self):
        h = MemoryHandler()
        h.handle(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started"))
        h.handle(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_completed"))
        self.assertEqual(len(h.find(event_name="cycle_started")), 1)

    def test_find_by_module_and_event_name(self):
        h = MemoryHandler()
        h.handle(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started"))
        h.handle(AgentEvent(module="Execution", family="planning", event_name="plan_started"))
        self.assertEqual(len(h.find(module="Cycle", event_name="cycle_started")), 1)


class TestHumanLogHandler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmp.name) / "activity.log"

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_to_file(self):
        h = HumanLogHandler(self.log_path)
        h.handle(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started", detail="Cycle #42"))
        h.flush()
        content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("CYCLE", content)
        self.assertIn("cycle_started", content)
        self.assertIn("Cycle #42", content)
        h.close()

    def test_includes_task_id(self):
        h = HumanLogHandler(self.log_path)
        h.handle(AgentEvent(module="Execution", family="tool_call", event_name="tool_call_succeeded", task_id="abc12345def", detail="edit_file x.py"))
        h.flush()
        content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("[abc12345]", content)
        h.close()

    def test_includes_success_icon(self):
        h = HumanLogHandler(self.log_path)
        h.handle(AgentEvent(module="Execution", family="verification", event_name="verification_completed", success=True, detail="all passed"))
        h.handle(AgentEvent(module="Execution", family="verification", event_name="verification_completed", success=False, detail="syntax error"))
        h.flush()
        content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("✓", content)
        self.assertIn("✗", content)
        h.close()

    def test_separator_line(self):
        h = HumanLogHandler(self.log_path)
        h.handle(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_separator"))
        h.flush()
        content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("━", content)
        h.close()

    def test_includes_reasoning(self):
        h = HumanLogHandler(self.log_path)
        h.handle(AgentEvent(module="LLM", family="audit_link", event_name="decision_recorded", detail="skip discovery", reasoning="queue is full"))
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
        h.handle(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started", cycle_id=42))
        h.handle(AgentEvent(module="Execution", family="tool_call", event_name="tool_call_succeeded", task_id="t1", success=True))
        h.flush()

        lines = self.log_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            data = json.loads(line)
            self.assertIn("module", data)
            self.assertIn("event_name", data)
        h.close()

    def test_omits_empty_fields(self):
        h = JsonLogHandler(self.log_path)
        h.handle(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started"))
        h.flush()
        data = json.loads(self.log_path.read_text(encoding="utf-8").strip())
        self.assertNotIn("task_id", data)
        self.assertNotIn("reasoning", data)
        h.close()

    def test_writes_new_envelope_fields(self):
        h = JsonLogHandler(self.log_path)
        h.handle(AgentEvent(
            module="Execution",
            family="tool_call",
            event_name="tool_call_succeeded",
            task_id="t1",
            thread_id="thread-1",
            llm_seq=7,
            data={
                "step_id": "step-1",
                "tool_call_id": "call-1",
                "tool_type": "filesystem",
                "tool_name": "read_file",
            },
        ))
        h.flush()
        data = json.loads(self.log_path.read_text(encoding="utf-8").strip())
        self.assertTrue(data["event_id"])
        self.assertEqual(data["module"], "Execution")
        self.assertEqual(data["family"], "tool_call")
        self.assertEqual(data["event_name"], "tool_call_succeeded")
        self.assertEqual(data["thread_id"], "thread-1")
        self.assertEqual(data["llm_seq"], 7)
        self.assertEqual(data["data"]["tool_name"], "read_file")
        h.close()


class TestStoreHandler(unittest.TestCase):
    def test_persists_to_store(self):
        store = MagicMock()
        h = StoreHandler(store)
        h.handle(AgentEvent(module="Execution", family="tool_call", event_name="tool_call_succeeded", task_id="t1", detail="edit x.py", success=True))
        store.add_event.assert_called_once()
        call_args = store.add_event.call_args
        self.assertEqual(call_args[0][0], "t1")
        self.assertIn("Execution.tool_call.tool_call_succeeded", call_args[0][1])
        self.assertIn("edit x.py", call_args[0][2])

    def test_skips_events_without_task_id(self):
        store = MagicMock()
        h = StoreHandler(store)
        h.handle(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started"))
        store.add_event.assert_not_called()


class TestObserver(unittest.TestCase):
    def test_dispatches_to_all_handlers(self):
        h1 = MemoryHandler()
        h2 = MemoryHandler()
        obs = Observer(handlers=[h1, h2])
        obs.emit(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started"))
        self.assertEqual(len(h1.events), 1)
        self.assertEqual(len(h2.events), 1)

    def test_handler_failure_does_not_stop_others(self):
        broken = MagicMock()
        broken.handle.side_effect = RuntimeError("boom")
        good = MemoryHandler()
        obs = Observer(handlers=[broken, good])
        obs.emit(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started"))
        self.assertEqual(len(good.events), 1)

    def test_convenience_cycle_start(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.cycle_start(42)
        self.assertEqual(len(h.events), 2)
        self.assertEqual(h.events[0].event_name, "cycle_separator")
        self.assertEqual(h.events[1].event_name, "cycle_started")
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
        self.assertEqual(h.events[0].module, "Execution")
        self.assertEqual(h.events[0].family, "planning")
        self.assertEqual(h.events[0].event_name, "plan_started")
        self.assertEqual(h.events[0].data["title"], "Fix bug")
        self.assertEqual(h.events[1].event_name, "plan_created")
        self.assertEqual(h.events[1].data["step_count"], 3)
        self.assertEqual(h.events[2].family, "tool_call")
        self.assertEqual(h.events[2].event_name, "tool_call_succeeded")
        self.assertEqual(h.events[2].data["tool_type"], "filesystem")
        self.assertEqual(h.events[2].data["tool_name"], "edit_file")
        self.assertEqual(h.events[4].event_name, "tool_call_failed")
        self.assertEqual(h.events[4].data["tool_type"], "command")
        self.assertEqual(h.events[5].family, "state")
        self.assertEqual(h.events[5].event_name, "execution_completed")
        fail_events = h.find(module="Execution", event_name="task_failed")
        self.assertEqual(len(fail_events), 1)
        self.assertFalse(fail_events[0].success)
        self.assertEqual(fail_events[0].module, "Execution")
        self.assertEqual(fail_events[0].family, "state")
        self.assertEqual(fail_events[0].event_name, "task_failed")

    def test_convenience_git_flow(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.git_worktree("t1", "agent/fix-bug", success=True)
        obs.git_committed("t1", "fix(parser): handle empty input")
        obs.git_pushed("t1")
        obs.git_pr("t1", "https://github.com/org/repo/pull/42", success=True)

        self.assertEqual(len(h.events), 4)
        pr = h.find(module="Execution", family="tool_call", event_name="tool_call_succeeded")
        self.assertGreaterEqual(len(pr), 1)
        pr = [event for event in pr if event.data.get("tool_name") == "git_create_pr"]
        self.assertEqual(len(pr), 1)
        self.assertTrue(pr[0].success)
        self.assertEqual(h.events[0].module, "Execution")
        self.assertEqual(h.events[0].family, "tool_call")
        self.assertEqual(h.events[0].event_name, "tool_call_succeeded")
        self.assertEqual(h.events[0].data["tool_type"], "git")
        self.assertEqual(h.events[0].data["tool_name"], "git_create_worktree")
        self.assertEqual(h.events[0].data["branch_name"], "agent/fix-bug")
        self.assertEqual(pr[0].module, "Execution")
        self.assertEqual(pr[0].family, "tool_call")
        self.assertEqual(pr[0].event_name, "tool_call_succeeded")
        self.assertEqual(pr[0].data["tool_name"], "git_create_pr")

    def test_decision_event(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.decision("Skip stale area", reasoning="Recently explored 2h ago")
        self.assertEqual(len(h.events), 1)
        self.assertEqual(h.events[0].module, "LLM")
        self.assertIn("Recently explored", h.events[0].reasoning)

    def test_llm_tool_selection_event(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.llm_tool_selection(
            task_id="t1",
            model="kimi-for-coding",
            tool_names=["read_file", "run_command"],
            prompt_tokens=120,
            completion_tokens=45,
            total_tokens=165,
        )
        self.assertEqual(len(h.events), 1)
        event = h.events[0]
        self.assertEqual(event.module, "LLM")
        self.assertEqual(event.family, "tool_selection")
        self.assertEqual(event.event_name, "tool_selection_recorded")
        self.assertEqual(event.data["tool_names"], ["read_file", "run_command"])
        self.assertEqual(event.data["prompt_tokens"], 120)

    def test_value_assessed(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.value_assessed("t1", "Fix bug in parser", 0.82, "execute")
        obs.value_assessed("t2", "Rename variable", 0.25, "skip")
        self.assertEqual(len(h.events), 2)
        self.assertTrue(h.events[0].success)
        self.assertFalse(h.events[1].success)


class TestDiscoveryObserverMethods(unittest.TestCase):
    def test_discover_strategy_emits_native_envelope_fields(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.discover_strategy("change_hotspot", 2, "Prefer neglected areas")

        strategy = h.find(module="Discovery", family="strategy", event_name="strategy_selected")
        self.assertEqual(len(strategy), 1)
        self.assertEqual(strategy[0].module, "Discovery")
        self.assertEqual(strategy[0].family, "strategy")
        self.assertEqual(strategy[0].event_name, "strategy_selected")
        self.assertEqual(strategy[0].data["strategy_name"], "change_hotspot")
        self.assertEqual(strategy[0].data["queue_depth"], 2)

    def test_discover_raw_candidates(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.discover_raw_candidates([
            {"id": "t1", "title": "Fix parser bug", "source": "todo_scan"},
            {"id": "t2", "title": "Add tests", "source": "test_gap"},
        ])
        found = h.find(module="Discovery", family="candidate", event_name="candidate_found")
        self.assertEqual(len(found), 2)
        self.assertIn("Fix parser bug", found[0].detail)
        self.assertIn("Add tests", found[1].detail)
        self.assertEqual(found[0].module, "Discovery")
        self.assertEqual(found[0].family, "candidate")
        self.assertEqual(found[0].event_name, "candidate_found")
        self.assertEqual(found[0].data["candidate_id"], "t1")
        self.assertEqual(found[0].data["source"], "todo_scan")

    def test_discover_value_scored(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.discover_value_scored("t1", "Fix parser bug", 0.82, "execute", "impact=0.9, scope=0.7")
        scored = h.find(module="Discovery", family="valuation", event_name="candidate_scored")
        self.assertEqual(len(scored), 1)
        self.assertIn("0.820", scored[0].detail)
        self.assertTrue(scored[0].success)
        self.assertIn("impact=0.9", scored[0].reasoning)

    def test_discover_value_scored_skip(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.discover_value_scored("t1", "Low value task", 0.15, "skip", "impact=0.1")
        scored = h.find(module="Discovery", family="valuation", event_name="candidate_scored")
        self.assertFalse(scored[0].success)

    def test_discover_filtered_out(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.discover_filtered_out("t1", "Rename variable", 0.15, "heuristic score too low")
        filtered = h.find(module="Discovery", family="valuation", event_name="candidate_filtered_out")
        self.assertEqual(len(filtered), 1)
        self.assertFalse(filtered[0].success)
        self.assertIn("heuristic", filtered[0].reasoning)
        self.assertEqual(filtered[0].module, "Discovery")
        self.assertEqual(filtered[0].family, "valuation")
        self.assertEqual(filtered[0].event_name, "candidate_filtered_out")
        self.assertEqual(filtered[0].data["score"], 0.15)
        self.assertEqual(filtered[0].data["filtered_reason"], "heuristic score too low")

    def test_discover_summary(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.discover_summary(raw=10, after_heuristic=6, after_llm=3, final=3)
        funnel = h.find(module="Discovery", family="funnel", event_name="funnel_summarized")
        self.assertEqual(len(funnel), 1)
        self.assertIn("raw=10", funnel[0].detail)
        self.assertIn("final=3", funnel[0].detail)
        self.assertEqual(funnel[0].module, "Discovery")
        self.assertEqual(funnel[0].family, "funnel")
        self.assertEqual(funnel[0].event_name, "funnel_summarized")
        self.assertEqual(funnel[0].data["raw_candidates"], 10)
        self.assertEqual(funnel[0].data["queued"], 3)

    def test_task_queued_emits_native_envelope_fields(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.task_queued("t1", "Fix parser bug", "todo_scan")

        queued = h.find(module="Discovery", family="queue", event_name="candidate_queued")
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0].module, "Discovery")
        self.assertEqual(queued[0].family, "queue")
        self.assertEqual(queued[0].event_name, "candidate_queued")
        self.assertEqual(queued[0].data["source"], "todo_scan")
        self.assertEqual(queued[0].data["title"], "Fix parser bug")

    def test_experience_injected(self):
        h = MemoryHandler()
        obs = Observer(handlers=[h])
        obs.experience_injected("t1", 3, "pattern A; pitfall B; insight C")
        injected = h.find(module="Memory", family="recall", event_name="experience_injected")
        self.assertEqual(len(injected), 1)
        self.assertIn("3 experiences", injected[0].detail)
        self.assertIn("pattern A", injected[0].reasoning)


class TestNullObserver(unittest.TestCase):
    def test_no_crash(self):
        obs = NullObserver()
        obs.cycle_start(1)
        obs.cycle_end(1, 0, 0, 0, 0)
        obs.emit(AgentEvent(module="X", family="general", event_name="y"))


class TestShortTime(unittest.TestCase):
    def test_valid_iso(self):
        result = _short_time("2026-03-05T14:30:22+00:00")
        self.assertEqual(result, "14:30:22")

    def test_invalid_falls_back(self):
        result = _short_time("garbage")
        self.assertRegex(result, r"\d{2}:\d{2}:\d{2}")


if __name__ == "__main__":
    unittest.main()

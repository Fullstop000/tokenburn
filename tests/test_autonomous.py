from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from llm247.ark_client import BudgetExhaustedError
from llm247.autonomous import (
    ActionResult,
    AgentAction,
    AutonomousAgent,
    AutonomousPlan,
    AutonomousPlanner,
    AutonomousStateStore,
    CommandSafetyPolicy,
    PlannerContext,
    run_autonomous_loop,
)
from llm247.reports import ReportWriter


class _FakeModelClient:
    """Deterministic planner model for JSON plan tests."""

    def __init__(self, output: str) -> None:
        self.output = output

    def generate_text(self, prompt: str) -> str:
        return self.output


class _FakePlanner:
    """Return one static plan for agent execution tests."""

    def build_plan(self, context: PlannerContext) -> AutonomousPlan:
        return AutonomousPlan(
            goal="Improve project quality",
            topic_query="autonomous software testing",
            actions=[AgentAction(action_type="run_command", command=["rg", "--files"])],
            rationale="Focus on immediate quality gains.",
        )


class _TwoActionPlanner:
    """Return deterministic two-step plan and count invocations."""

    def __init__(self) -> None:
        self.call_count = 0

    def build_plan(self, context: PlannerContext) -> AutonomousPlan:
        self.call_count += 1
        return AutonomousPlan(
            goal="Process TODO backlog",
            topic_query="todo triage strategy",
            actions=[
                AgentAction(action_type="run_command", command=["rg", "--files"]),
                AgentAction(action_type="write_file", path="notes/todo.md", content="done"),
            ],
            rationale="Finish two actions reliably.",
        )


class _BudgetExhaustedPlanner:
    """Raise budget-exhausted on each planning call."""

    def build_plan(self, context: PlannerContext) -> AutonomousPlan:
        raise BudgetExhaustedError("token budget exhausted")


class _FakeExecutor:
    """Record actions and produce deterministic action results."""

    def __init__(self) -> None:
        self.actions: List[AgentAction] = []

    def execute(self, action: AgentAction, workspace_path: Path) -> ActionResult:
        self.actions.append(action)
        return ActionResult(
            action_type=action.action_type,
            success=True,
            output="ok",
        )


class _FailOnceExecutor:
    """Raise once to simulate shutdown/crash mid-cycle."""

    def __init__(self) -> None:
        self.fail_once = True
        self.actions: List[AgentAction] = []

    def execute(self, action: AgentAction, workspace_path: Path) -> ActionResult:
        self.actions.append(action)
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("simulated-shutdown")
        return ActionResult(action_type=action.action_type, success=True, output="ok")


class AutonomousPlannerTests(unittest.TestCase):
    """Validate JSON plan parsing and policy constraints."""

    def test_build_plan_parses_json_and_limits_actions(self) -> None:
        """Planner should parse model JSON and cap action count."""
        model_output = """
        {
          "goal": "Build autonomous engineering loop",
          "topic_query": "llm agent safety techniques",
          "rationale": "High leverage and relevant.",
          "actions": [
            {"type": "search_web", "query": "llm agent safety techniques"},
            {"type": "run_command", "command": ["rg", "--files"]},
            {"type": "run_command", "command": ["git", "status"]}
          ]
        }
        """
        planner = AutonomousPlanner(model_client=_FakeModelClient(model_output), max_actions=2)
        context = PlannerContext(
            workspace_path=Path("/tmp/demo"),
            now=datetime(2026, 3, 4, 0, 0, tzinfo=timezone.utc),
            workspace_summary="summary",
            previous_goal="",
            previous_topic_query="",
            last_cycle_observations="",
            recent_reports="",
        )

        plan = planner.build_plan(context)

        self.assertEqual("Build autonomous engineering loop", plan.goal)
        self.assertEqual(2, len(plan.actions))
        self.assertEqual("search_web", plan.actions[0].action_type)


class CommandSafetyPolicyTests(unittest.TestCase):
    """Verify command allow-list and dangerous command blocking."""

    def test_blocks_dangerous_commands(self) -> None:
        """Policy should reject shell-dangerous command patterns."""
        policy = CommandSafetyPolicy()

        allowed, _ = policy.is_allowed(["rg", "--files"])
        denied_rm, _ = policy.is_allowed(["rm", "-rf", "/"])
        denied_git_reset, _ = policy.is_allowed(["git", "reset", "--hard"])

        self.assertTrue(allowed)
        self.assertFalse(denied_rm)
        self.assertFalse(denied_git_reset)


class AutonomousAgentTests(unittest.TestCase):
    """Cover end-to-end autonomous cycle mechanics."""

    def test_run_once_generates_report_and_updates_state(self) -> None:
        """One cycle should persist state and emit a markdown report."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_writer = ReportWriter(root / "reports")
            state_store = AutonomousStateStore(root / ".llm247" / "autonomous_state.json")
            planner = _FakePlanner()
            executor = _FakeExecutor()
            agent = AutonomousAgent(
                workspace_path=root,
                planner=planner,
                executor=executor,
                state_store=state_store,
                report_writer=report_writer,
            )

            now = datetime(2026, 3, 4, 0, 0, tzinfo=timezone.utc)
            report_path = agent.run_once(now=now)
            state = state_store.load()

            self.assertTrue(report_path.exists())
            self.assertEqual("Improve project quality", state.active_goal)
            self.assertEqual("Improve project quality", state.current_task)
            self.assertEqual("completed", state.status)
            self.assertEqual(1, state.progress_completed_actions)
            self.assertEqual(1, state.progress_total_actions)
            self.assertEqual(1, state.current_task_iteration)
            self.assertGreaterEqual(state.current_task_elapsed_seconds, 0.0)
            self.assertEqual(1, state.cycle_count)
            self.assertEqual(1, len(executor.actions))

    def test_loop_stops_when_budget_exhausted(self) -> None:
        """Agent loop should stop immediately on token-budget exhaustion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_writer = ReportWriter(root / "reports")
            state_store = AutonomousStateStore(root / ".llm247" / "autonomous_state.json")
            planner = _BudgetExhaustedPlanner()
            executor = _FakeExecutor()
            agent = AutonomousAgent(
                workspace_path=root,
                planner=planner,
                executor=executor,
                state_store=state_store,
                report_writer=report_writer,
            )

            stop_reason = run_autonomous_loop(
                agent=agent,
                poll_interval_seconds=1,
                max_cycles=3,
                sleeper=lambda _seconds: None,
            )
            state = state_store.load()

            self.assertEqual("budget_exhausted", stop_reason)
            self.assertEqual("budget_exhausted", state.stop_reason)

    def test_resumes_pending_actions_after_interruption(self) -> None:
        """Agent should resume unfinished action list after a shutdown-like failure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_writer = ReportWriter(root / "reports")
            state_store = AutonomousStateStore(root / ".llm247" / "autonomous_state.json")
            planner = _TwoActionPlanner()
            fail_once_executor = _FailOnceExecutor()
            agent = AutonomousAgent(
                workspace_path=root,
                planner=planner,
                executor=fail_once_executor,
                state_store=state_store,
                report_writer=report_writer,
            )

            with self.assertRaises(RuntimeError):
                agent.run_once(now=datetime(2026, 3, 4, 0, 0, tzinfo=timezone.utc))

            state_after_fail = state_store.load()
            self.assertGreater(len(state_after_fail.pending_actions), 0)
            self.assertEqual("Process TODO backlog", state_after_fail.current_task)
            self.assertEqual("running", state_after_fail.status)
            self.assertEqual(0, state_after_fail.progress_completed_actions)
            self.assertEqual(2, state_after_fail.progress_total_actions)
            self.assertEqual(1, state_after_fail.current_task_iteration)
            self.assertGreaterEqual(state_after_fail.current_task_elapsed_seconds, 0.0)

            resume_executor = _FakeExecutor()
            resumed_agent = AutonomousAgent(
                workspace_path=root,
                planner=planner,
                executor=resume_executor,
                state_store=state_store,
                report_writer=report_writer,
            )
            report_path = resumed_agent.run_once(now=datetime(2026, 3, 4, 0, 1, tzinfo=timezone.utc))
            final_state = state_store.load()

            self.assertTrue(report_path.exists())
            self.assertEqual([], final_state.pending_actions)
            self.assertEqual("completed", final_state.status)
            self.assertEqual(2, final_state.progress_completed_actions)
            self.assertEqual(2, final_state.progress_total_actions)
            self.assertEqual(1, final_state.current_task_iteration)
            self.assertGreaterEqual(final_state.current_task_elapsed_seconds, 0.0)
            self.assertEqual(1, final_state.cycle_count)
            self.assertEqual(1, planner.call_count)
            self.assertGreaterEqual(len(resume_executor.actions), 1)


if __name__ == "__main__":
    unittest.main()

"""Tests for Plan-Execute-Replan execution model."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from llm247_v2.agent import AutonomousAgentV2
from llm247_v2.core.constitution import load_constitution
from llm247_v2.core.directive import load_directive, save_directive
from llm247_v2.core.models import (
    Directive,
    ExecutionRound,
    PlanStep,
    Task,
    TaskPlan,
    TaskSourceConfig,
    TaskStatus,
)
from llm247_v2.execution.executor import ExecutionResult
from llm247_v2.execution.planner import (
    format_execution_history_for_replan,
    replan_task_with_constitution,
    serialize_plan,
)
from llm247_v2.execution.verifier import CheckResult, VerificationResult
from llm247_v2.observability.observer import MemoryHandler, Observer
from llm247_v2.storage.store import TaskStore


# ──────────────────────────────────────────────
# Test helpers
# ──────────────────────────────────────────────


class FakeLLM:
    """LLM stub that returns configurable responses."""

    def __init__(self, responses=None):
        self.call_count = 0
        self._responses = list(responses or [])
        self.tracker = None

    def generate(self, prompt: str) -> str:
        self.call_count += 1
        if self._responses:
            return self._responses.pop(0)
        return json.dumps({
            "steps": [
                {"action": "edit_file", "target": "src/fix.py",
                 "content": "fixed", "description": "fix the issue"},
            ],
            "commit_message": "fix(core): correct the issue",
            "pr_title": "Fix issue",
            "pr_body": "## Summary\n- Fixed the issue",
        })


def _make_plan(task_id="t1", steps=None, commit_msg="fix: test"):
    return TaskPlan(
        task_id=task_id,
        steps=steps or [PlanStep(action="edit_file", target="src/a.py", content="x=1", description="edit")],
        commit_message=commit_msg,
        pr_title="Test",
        pr_body="body",
    )


def _make_result(idx=0, action="edit_file", target="src/a.py", success=True, output="ok"):
    return ExecutionResult(step_index=idx, action=action, target=target, success=success, output=output)


def _passing_verification():
    return VerificationResult(
        passed=True,
        checks=[CheckResult(name="tests", passed=True, output="ok")],
        summary="tests: PASS",
    )


def _failing_verification():
    return VerificationResult(
        passed=False,
        checks=[
            CheckResult(name="tests", passed=False, output="AssertionError: expected 1 got 2"),
            CheckResult(name="syntax", passed=True, output="ok"),
        ],
        summary="tests: FAIL | syntax: PASS",
    )


class AgentTestBase(unittest.TestCase):
    """Shared setup for agent-level tests."""

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

        self.directive = Directive(
            task_sources={
                "todo_scan": TaskSourceConfig(enabled=False),
                "test_gap": TaskSourceConfig(enabled=False),
                "lint_check": TaskSourceConfig(enabled=False),
                "self_improvement": TaskSourceConfig(enabled=False),
            },
        )
        save_directive(self.directive_path, self.directive)

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

    def _insert_queued_task(self, task_id="replan-1", title="Fix bug"):
        task = Task(
            id=task_id,
            title=title,
            description="Fix a test bug",
            source="manual",
            status=TaskStatus.QUEUED.value,
            priority=1,
        )
        self.store.insert_task(task)
        return task


# ──────────────────────────────────────────────
# 1. Model tests
# ──────────────────────────────────────────────


class TestExecutionRoundModel(unittest.TestCase):
    def test_creation(self):
        er = ExecutionRound(
            round_number=0,
            plan_steps=[{"action": "edit_file", "target": "a.py"}],
            results=[{"step_index": 0, "success": True}],
            verification="PASS",
            trigger="step_failure",
            token_cost=100,
        )
        self.assertEqual(er.round_number, 0)
        self.assertEqual(er.trigger, "step_failure")
        self.assertEqual(er.token_cost, 100)

    def test_default_token_cost(self):
        er = ExecutionRound(
            round_number=1,
            plan_steps=[],
            results=[],
            verification="",
            trigger="verification_failure",
        )
        self.assertEqual(er.token_cost, 0)


class TestTaskReplanHistory(unittest.TestCase):
    def test_default_empty(self):
        task = Task(id="t", title="t", description="d", source="s")
        self.assertEqual(task.replan_history, "")


class TestDirectiveNewFields(unittest.TestCase):
    def test_defaults(self):
        d = Directive()
        self.assertEqual(d.max_replan_rounds, 3)
        self.assertEqual(d.max_tokens_per_task, 0)

    def test_custom_values(self):
        d = Directive(max_replan_rounds=5, max_tokens_per_task=50000)
        self.assertEqual(d.max_replan_rounds, 5)
        self.assertEqual(d.max_tokens_per_task, 50000)


# ──────────────────────────────────────────────
# 2. Planner tests
# ──────────────────────────────────────────────


class TestReplanTaskWithConstitution(unittest.TestCase):
    def test_calls_llm_with_replan_template(self):
        llm = FakeLLM()
        task = Task(id="t1", title="Fix bug", description="desc", source="manual")
        constitution = load_constitution(Path("/nonexistent"))
        directive = Directive()

        plan = replan_task_with_constitution(
            task=task,
            workspace=Path("/tmp"),
            directive=directive,
            constitution=constitution,
            llm=llm,
            executed_steps="[0] FAIL edit_file src/a.py\n    error details",
            verification_output="",
            trigger="step_failure",
            round_number=1,
            remaining_rounds=2,
        )

        self.assertEqual(llm.call_count, 1)
        self.assertIsInstance(plan, TaskPlan)
        self.assertGreater(len(plan.steps), 0)


class TestFormatExecutionHistoryForReplan(unittest.TestCase):
    def test_successful_write_step_omits_content(self):
        results = [_make_result(0, "edit_file", "a.py", True, "wrote 100 bytes")]
        output = format_execution_history_for_replan(results)
        self.assertIn("file written successfully", output)
        self.assertNotIn("wrote 100 bytes", output)

    def test_failed_step_includes_output(self):
        results = [_make_result(0, "run_command", "pytest", False, "FAILED test_foo")]
        output = format_execution_history_for_replan(results)
        self.assertIn("FAIL", output)
        self.assertIn("FAILED test_foo", output)

    def test_mixed_results(self):
        results = [
            _make_result(0, "edit_file", "a.py", True, "wrote 50 bytes"),
            _make_result(1, "run_command", "pytest", False, "1 failed"),
        ]
        output = format_execution_history_for_replan(results)
        self.assertIn("[0] OK edit_file a.py (file written successfully)", output)
        self.assertIn("[1] FAIL run_command pytest", output)
        self.assertIn("1 failed", output)

    def test_empty_results(self):
        output = format_execution_history_for_replan([])
        self.assertEqual(output, "")


# ──────────────────────────────────────────────
# 3. Observer tests
# ──────────────────────────────────────────────


class TestObserverReplanEmitters(unittest.TestCase):
    def setUp(self):
        self.handler = MemoryHandler()
        self.obs = Observer(handlers=[self.handler])

    def test_replan_triggered(self):
        self.obs.replan_triggered("t1", 1, "step_failure")
        events = self.handler.find(phase="plan", action="replan_triggered")
        self.assertEqual(len(events), 1)
        self.assertIn("round=1", events[0].detail)
        self.assertIn("step_failure", events[0].detail)

    def test_replan_created(self):
        self.obs.replan_created("t1", 1, 3)
        events = self.handler.find(phase="plan", action="replan_created")
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].success)
        self.assertIn("steps=3", events[0].detail)

    def test_replan_exhausted(self):
        self.obs.replan_exhausted("t1", 3)
        events = self.handler.find(phase="plan", action="replan_exhausted")
        self.assertEqual(len(events), 1)
        self.assertFalse(events[0].success)
        self.assertIn("3 rounds", events[0].detail)


# ──────────────────────────────────────────────
# 4. Agent loop — happy path (fail round 0, succeed round 1)
# ──────────────────────────────────────────────


class TestReplanHappyPath(AgentTestBase):
    def test_execution_fails_round0_replan_succeeds_round1(self):
        task = self._insert_queued_task()
        plan = _make_plan(task.id)
        replan = _make_plan(task.id, steps=[
            PlanStep(action="edit_file", target="src/fix.py", content="fixed", description="fix"),
        ])

        failed_result = _make_result(0, "edit_file", "src/a.py", False, "write error")
        ok_result = _make_result(0, "edit_file", "src/fix.py", True, "wrote 5 bytes")
        directive = Directive()
        constitution = load_constitution(self.constitution_path)

        with patch("llm247_v2.agent.plan_task_with_constitution", return_value=plan):
            with patch("llm247_v2.agent.replan_task_with_constitution", return_value=replan):
                with patch("llm247_v2.agent.verify_task", return_value=_passing_verification()):
                    with patch("llm247_v2.agent.PlanExecutor") as MockExec:
                        MockExec.return_value.execute_plan.side_effect = [
                            (False, [failed_result]),
                            (True, [ok_result]),
                        ]
                        with patch.object(self.agent, "_cleanup_worktree"):
                            success = self.agent._execute_single_task(task, directive, constitution)

        self.assertTrue(success)
        updated = self.store.get_task(task.id)
        self.assertEqual(updated.status, TaskStatus.COMPLETED.value)

        # Check replan events were emitted
        triggered = self.memory_handler.find(phase="plan", action="replan_triggered")
        self.assertEqual(len(triggered), 1)
        created = self.memory_handler.find(phase="plan", action="replan_created")
        self.assertEqual(len(created), 1)


# ──────────────────────────────────────────────
# 5. Agent loop — verification failure triggers replan
# ──────────────────────────────────────────────


class TestReplanVerificationFailure(AgentTestBase):
    def test_verification_fails_round0_replan_fixes(self):
        task = self._insert_queued_task()
        plan = _make_plan(task.id)
        replan = _make_plan(task.id)

        ok_result = _make_result(0, "edit_file", "src/a.py", True, "wrote 3 bytes")
        directive = Directive()
        constitution = load_constitution(self.constitution_path)

        with patch("llm247_v2.agent.plan_task_with_constitution", return_value=plan):
            with patch("llm247_v2.agent.replan_task_with_constitution", return_value=replan):
                with patch("llm247_v2.agent.verify_task") as mock_verify:
                    mock_verify.side_effect = [
                        _failing_verification(),
                        _passing_verification(),
                    ]
                    with patch("llm247_v2.agent.PlanExecutor") as MockExec:
                        MockExec.return_value.execute_plan.return_value = (True, [ok_result])
                        with patch.object(self.agent, "_cleanup_worktree"):
                            success = self.agent._execute_single_task(task, directive, constitution)

        self.assertTrue(success)
        triggered = self.memory_handler.find(phase="plan", action="replan_triggered")
        self.assertEqual(len(triggered), 1)
        self.assertIn("verification_failure", triggered[0].detail)


# ──────────────────────────────────────────────
# 6. Agent loop — exhausted (all rounds fail)
# ──────────────────────────────────────────────


class TestReplanExhausted(AgentTestBase):
    def test_all_rounds_fail_needs_human(self):
        task = self._insert_queued_task()
        plan = _make_plan(task.id)
        directive = Directive(max_replan_rounds=2)
        constitution = load_constitution(self.constitution_path)

        failed_result = _make_result(0, "edit_file", "src/a.py", False, "write error")

        with patch("llm247_v2.agent.plan_task_with_constitution", return_value=plan):
            with patch("llm247_v2.agent.replan_task_with_constitution", return_value=plan):
                with patch("llm247_v2.agent.PlanExecutor") as MockExec:
                    MockExec.return_value.execute_plan.return_value = (False, [failed_result])
                    with patch.object(self.agent, "_cleanup_worktree"):
                        success = self.agent._execute_single_task(task, directive, constitution)

        self.assertFalse(success)
        updated = self.store.get_task(task.id)
        self.assertEqual(updated.status, TaskStatus.NEEDS_HUMAN.value)
        self.assertTrue(updated.replan_history)

        exhausted = self.memory_handler.find(phase="plan", action="replan_exhausted")
        self.assertEqual(len(exhausted), 1)


# ──────────────────────────────────────────────
# 7. Agent loop — constitution block (no retry)
# ──────────────────────────────────────────────


class TestReplanConstitutionBlock(AgentTestBase):
    def test_constitution_block_no_replan(self):
        task = self._insert_queued_task()
        # Use a target that the default constitution will block (immutable path)
        plan = _make_plan(task.id, steps=[
            PlanStep(action="edit_file", target="constitution.md", content="hacked", description="bad"),
        ])
        directive = Directive()
        constitution = load_constitution(self.constitution_path)

        # Patch at class level since Constitution is a frozen dataclass
        with patch("llm247_v2.agent.plan_task_with_constitution", return_value=plan):
            with patch("llm247_v2.core.constitution.Constitution.check_action_allowed", return_value=(False, "immutable path")):
                with patch.object(self.agent, "_cleanup_worktree"):
                    success = self.agent._execute_single_task(task, directive, constitution)

        self.assertFalse(success)
        updated = self.store.get_task(task.id)
        self.assertEqual(updated.status, TaskStatus.NEEDS_HUMAN.value)

        # No replan events — constitution block is immediate
        triggered = self.memory_handler.find(phase="plan", action="replan_triggered")
        self.assertEqual(len(triggered), 0)


# ──────────────────────────────────────────────
# 8. Agent loop — token budget exceeded
# ──────────────────────────────────────────────


class TestReplanTokenBudget(AgentTestBase):
    def test_token_budget_stops_replan(self):
        task = self._insert_queued_task()
        plan = _make_plan(task.id)
        directive = Directive(max_replan_rounds=3, max_tokens_per_task=100)
        constitution = load_constitution(self.constitution_path)

        failed_result = _make_result(0, "edit_file", "src/a.py", False, "write error")

        # Simulate token tracker that reports over-budget after first round.
        # snapshot() calls: (1) token_before, (2) _is_task_token_budget_exceeded, (3) _finalize_costs.
        tracker = MagicMock()
        tracker.snapshot.side_effect = [
            {"total_tokens": 0},    # token_before
            {"total_tokens": 200},  # budget check: 200 - 0 = 200 > 100
            {"total_tokens": 200},  # finalize_costs
        ]

        with patch("llm247_v2.agent._get_tracker", return_value=tracker):
            with patch("llm247_v2.agent.plan_task_with_constitution", return_value=plan):
                with patch("llm247_v2.agent.PlanExecutor") as MockExec:
                    MockExec.return_value.execute_plan.return_value = (False, [failed_result])
                    with patch.object(self.agent, "_cleanup_worktree"):
                        success = self.agent._execute_single_task(task, directive, constitution)

        self.assertFalse(success)
        updated = self.store.get_task(task.id)
        self.assertEqual(updated.status, TaskStatus.NEEDS_HUMAN.value)

        # Token budget exceeded — replan not triggered, immediate exhaust
        exhausted = self.memory_handler.find(phase="plan", action="replan_exhausted")
        self.assertEqual(len(exhausted), 1)


# ──────────────────────────────────────────────
# 9. max_replan_rounds=1 — equivalent to one-shot
# ──────────────────────────────────────────────


class TestOneShotBackwardCompat(AgentTestBase):
    def test_max_replan_rounds_1_is_oneshot(self):
        task = self._insert_queued_task()
        plan = _make_plan(task.id)
        directive = Directive(max_replan_rounds=1)
        constitution = load_constitution(self.constitution_path)

        failed_result = _make_result(0, "edit_file", "src/a.py", False, "write error")

        with patch("llm247_v2.agent.plan_task_with_constitution", return_value=plan):
            with patch("llm247_v2.agent.PlanExecutor") as MockExec:
                MockExec.return_value.execute_plan.return_value = (False, [failed_result])
                with patch.object(self.agent, "_cleanup_worktree"):
                    success = self.agent._execute_single_task(task, directive, constitution)

        self.assertFalse(success)
        updated = self.store.get_task(task.id)
        self.assertEqual(updated.status, TaskStatus.NEEDS_HUMAN.value)

        # No replan triggered — only 1 round allowed, no retry
        triggered = self.memory_handler.find(phase="plan", action="replan_triggered")
        self.assertEqual(len(triggered), 0)


# ──────────────────────────────────────────────
# 10. Storage — migration, insert/update/read round-trips
# ──────────────────────────────────────────────


class TestStorageReplanHistory(unittest.TestCase):
    def test_replan_history_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStore(Path(tmp) / "tasks.db")
            try:
                task = Task(
                    id="rp-store-1",
                    title="Storage test",
                    description="test replan_history persistence",
                    source="manual",
                    replan_history='[{"round_number": 0, "trigger": "step_failure"}]',
                )
                store.insert_task(task)

                loaded = store.get_task("rp-store-1")
                self.assertEqual(
                    loaded.replan_history,
                    '[{"round_number": 0, "trigger": "step_failure"}]',
                )

                loaded.replan_history = '[{"round_number": 0}, {"round_number": 1}]'
                store.update_task(loaded)

                reloaded = store.get_task("rp-store-1")
                self.assertEqual(
                    reloaded.replan_history,
                    '[{"round_number": 0}, {"round_number": 1}]',
                )
            finally:
                store.close()

    def test_migration_adds_column(self):
        """Verify that opening a store on a DB without replan_history column works."""
        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStore(Path(tmp) / "tasks.db")
            try:
                task = Task(id="mig-1", title="t", description="d", source="s")
                store.insert_task(task)
                loaded = store.get_task("mig-1")
                self.assertEqual(loaded.replan_history, "")
            finally:
                store.close()


# ──────────────────────────────────────────────
# 11. Directive persistence round-trip
# ──────────────────────────────────────────────


class TestDirectivePersistence(unittest.TestCase):
    def test_save_and_load_replan_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "directive.json"
            d = Directive(max_replan_rounds=5, max_tokens_per_task=25000)
            save_directive(path, d)

            loaded = load_directive(path)
            self.assertEqual(loaded.max_replan_rounds, 5)
            self.assertEqual(loaded.max_tokens_per_task, 25000)

    def test_defaults_when_missing_from_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "directive.json"
            # Write JSON without the new fields
            path.write_text('{"paused": false}', encoding="utf-8")
            loaded = load_directive(path)
            self.assertEqual(loaded.max_replan_rounds, 3)
            self.assertEqual(loaded.max_tokens_per_task, 0)


if __name__ == "__main__":
    unittest.main()

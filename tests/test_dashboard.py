from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from llm247.autonomous import AgentAction, AutonomousState, AutonomousStateStore
from llm247.dashboard import build_task_snapshot, render_dashboard_html
from llm247.storage import TaskStateStore


class DashboardSnapshotTests(unittest.TestCase):
    """Validate task snapshot aggregation for control plane API."""

    def test_includes_autonomous_and_legacy_tasks(self) -> None:
        """Snapshot should include autonomous progress and legacy task rows together."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            autonomous_state_path = workspace / ".llm247" / "autonomous_state.json"
            legacy_state_path = workspace / ".llm247" / "state.json"

            autonomous_store = AutonomousStateStore(autonomous_state_path)
            autonomous_store.save(
                AutonomousState(
                    active_goal="Sort TODO backlog",
                    current_task="Sort TODO backlog",
                    current_task_iteration=3,
                    current_task_elapsed_seconds=12.5,
                    progress_completed_actions=1,
                    progress_total_actions=3,
                    status="running",
                    pending_goal="Sort TODO backlog",
                    pending_topic_query="todo triage",
                    pending_rationale="Continue unfinished work",
                    pending_actions=[
                        AgentAction(action_type="run_command", command=["rg", "--files"]),
                        AgentAction(action_type="write_file", path="notes/todo.md", content="next"),
                    ],
                    updated_at="2026-03-04T00:00:00+00:00",
                )
            )

            legacy_store = TaskStateStore(legacy_state_path)
            now = datetime(2026, 3, 4, 0, 0, tzinfo=timezone.utc)
            legacy_store.mark_run("engineering_watchdog", now - timedelta(minutes=45), duration_seconds=1.2)
            legacy_store.mark_run("engineering_watchdog", now - timedelta(minutes=40), duration_seconds=0.8)
            legacy_store.mark_run("token_efficiency_guard", now - timedelta(minutes=30), duration_seconds=2.3)

            snapshot = build_task_snapshot(
                workspace_path=workspace,
                autonomous_state_path=autonomous_state_path,
                legacy_state_path=legacy_state_path,
                now=now,
            )

            task_ids = {task["id"] for task in snapshot["tasks"]}
            self.assertIn("autonomous.current", task_ids)
            self.assertIn("autonomous.pending.1", task_ids)
            self.assertIn("legacy.engineering_watchdog", task_ids)
            self.assertIn("legacy.token_efficiency_guard", task_ids)

            autonomous_current = next(task for task in snapshot["tasks"] if task["id"] == "autonomous.current")
            self.assertEqual("running", autonomous_current["status"])
            self.assertEqual("1/3", autonomous_current["progress"])
            self.assertEqual(3, autonomous_current["iteration"])
            self.assertAlmostEqual(12.5, autonomous_current["elapsed_seconds"], places=2)

            legacy_watchdog = next(task for task in snapshot["tasks"] if task["id"] == "legacy.engineering_watchdog")
            self.assertEqual("due", legacy_watchdog["status"])
            self.assertEqual(2, legacy_watchdog["iteration"])
            self.assertAlmostEqual(2.0, legacy_watchdog["elapsed_seconds"], places=2)

            legacy_efficiency = next(task for task in snapshot["tasks"] if task["id"] == "legacy.token_efficiency_guard")
            self.assertEqual("waiting", legacy_efficiency["status"])
            self.assertEqual(1, legacy_efficiency["iteration"])
            self.assertAlmostEqual(2.3, legacy_efficiency["elapsed_seconds"], places=2)

    def test_handles_missing_state_files(self) -> None:
        """Snapshot generation should not fail when state files are absent."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            snapshot = build_task_snapshot(
                workspace_path=workspace,
                autonomous_state_path=workspace / ".llm247" / "autonomous_state.json",
                legacy_state_path=workspace / ".llm247" / "state.json",
                now=datetime(2026, 3, 4, 0, 0, tzinfo=timezone.utc),
            )

            self.assertIn("tasks", snapshot)
            self.assertGreaterEqual(len(snapshot["tasks"]), 2)


class DashboardHtmlTests(unittest.TestCase):
    """Validate static dashboard page rendering."""

    def test_render_dashboard_contains_expected_mounts(self) -> None:
        """Page should provide title and task table mount points."""
        html = render_dashboard_html()
        self.assertIn("llm247 Control Plane", html)
        self.assertIn("id=\"task-table-body\"", html)
        self.assertIn("/api/tasks", html)


if __name__ == "__main__":
    unittest.main()

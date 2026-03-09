import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from llm247_v2.dashboard.server import (
    _api_bootstrap_status,
    _api_default_model,
    _api_discovery,
    _api_delete_model,
    _api_experiences,
    _api_help_center,
    _api_inject_task,
    _api_models,
    _api_register_model,
    _api_update_model,
    _api_resolve_help_request,
    _api_set_model_bindings,
    _api_set_paused,
    _api_summary,
    _api_stats,
    _api_task_detail,
    _api_tasks,
    _task_full,
    _task_row,
    serve_dashboard,
)
from llm247_v2.core.directive import load_directive, save_directive
from llm247_v2.core.models import Directive, ModelBindingPoint, ModelType, Task, TaskStatus
from llm247_v2.storage.model_registry import ModelRegistryStore
from llm247_v2.storage.store import TaskStore
from llm247_v2.storage.experience import Experience, ExperienceStore
from llm247_v2.storage.thread_store import ThreadStore


class TestDashboardAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        self.store = TaskStore(self.db_path)
        self.exp_store = ExperienceStore(Path(self.tmp.name) / "experience.db")
        self.model_store = ModelRegistryStore(Path(self.tmp.name) / "models.db")
        self.directive_path = Path(self.tmp.name) / "directive.json"
        save_directive(self.directive_path, Directive())

    def tearDown(self):
        self.store.close()
        self.exp_store.close()
        self.model_store.close()
        self.tmp.cleanup()

    def test_api_tasks_empty(self):
        result = _api_tasks(self.store)
        self.assertIn("tasks", result)
        self.assertEqual(len(result["tasks"]), 0)

    def test_api_tasks_with_data(self):
        self.store.insert_task(Task(
            id="t1", title="Test", description="D", source="manual",
            status="queued", priority=2,
        ))
        result = _api_tasks(self.store)
        self.assertEqual(len(result["tasks"]), 1)
        self.assertEqual(result["tasks"][0]["title"], "Test")

    def test_api_tasks_includes_pr_status_metadata(self):
        self.store.insert_task(Task(
            id="t-pr",
            title="Task with PR",
            description="D",
            source="manual",
            status="completed",
            priority=2,
            pr_url="https://github.com/Fullstop000/sprout/pull/42",
        ))

        result = _api_tasks(
            self.store,
            pr_status_resolver=lambda _url: {
                "pr_number": 42,
                "pr_status": "merged",
                "pr_title": "Fix dashboard tokens",
            },
        )

        self.assertEqual(result["tasks"][0]["pr_number"], 42)
        self.assertEqual(result["tasks"][0]["pr_status"], "merged")
        self.assertEqual(result["tasks"][0]["pr_title"], "Fix dashboard tokens")

    def test_api_stats(self):
        self.store.insert_task(Task(
            id="t1", title="T", description="D", source="manual",
            status="completed", priority=2,
            prompt_token_cost=120,
            completion_token_cost=45,
            token_cost=165,
        ))
        stats = _api_stats(self.store)
        self.assertEqual(stats["total_tasks"], 1)
        self.assertIn("completed", stats["status_counts"])
        self.assertEqual(stats["input_tokens"], 120)
        self.assertEqual(stats["output_tokens"], 45)
        self.assertEqual(stats["total_tokens"], 165)

    def test_api_summary_includes_briefing_changes_and_attention(self):
        thread_store = ThreadStore(Path(self.tmp.name) / "threads.db")
        task = Task(
            id="t-summary",
            title="Review dashboard summary",
            description="refresh homepage",
            source="manual",
            status=TaskStatus.NEEDS_HUMAN.value,
            priority=1,
            prompt_token_cost=120,
            completion_token_cost=45,
            token_cost=165,
            human_help_request="Need a human decision on summary wording.",
        )
        self.store.insert_task(task)
        self.store.add_event(task.id, "Execution.state.task_needs_human", "Task needs human review")

        activity_path = Path(self.tmp.name) / "activity.jsonl"
        activity_path.write_text(
            json.dumps({
                "module": "Execution",
                "family": "state",
                "event_name": "task_needs_human",
                "task_id": task.id,
                "timestamp": "2026-03-08T10:00:00+00:00",
                "detail": "Task needs human review",
                "reasoning": "Verification evidence is incomplete.",
            }) + "\n",
            encoding="utf-8",
        )

        thread = thread_store.create_thread("Need reply", "human", "Can you review this?")
        thread_store.set_status(thread.id, "waiting_reply")

        payload = _api_summary(
            self.store,
            self.directive_path,
            Path(self.tmp.name),
            model_store=self.model_store,
            thread_store=thread_store,
        )

        self.assertEqual(payload["briefing"]["metrics"][0]["label"], "Input tokens")
        self.assertEqual(payload["briefing"]["metrics"][0]["value"], "120")
        self.assertTrue(any(item["label"] == "Needs human" for item in payload["attention"]))
        self.assertTrue(any(item["label"] == "Inbox" for item in payload["attention"]))
        self.assertEqual(payload["changes"][0]["action"]["kind"], "task")
        self.assertEqual(payload["changes"][0]["action"]["taskId"], task.id)
        self.assertTrue(any(item["page"] == "inbox" for item in payload["destinations"]))
        thread_store.close()

    def test_inject_task(self):
        result = _api_inject_task(self.store, {"title": "Manual task", "priority": 1})
        self.assertEqual(result["status"], "ok")
        tasks = self.store.list_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].title, "Manual task")

    def test_inject_no_title(self):
        result = _api_inject_task(self.store, {})
        self.assertIn("error", result)

    def test_help_center_lists_only_needs_human(self):
        needs_help = Task(
            id="h1",
            title="Needs Human",
            description="blocked",
            source="manual",
            status=TaskStatus.NEEDS_HUMAN.value,
            priority=1,
            human_help_request="Please resolve credentials issue in runtime env.",
        )
        normal = Task(
            id="q1",
            title="Queued",
            description="normal",
            source="manual",
            status=TaskStatus.QUEUED.value,
            priority=2,
        )
        self.store.insert_task(needs_help)
        self.store.insert_task(normal)

        result = _api_help_center(self.store)
        self.assertEqual(len(result["requests"]), 1)
        self.assertEqual(result["requests"][0]["id"], "h1")
        self.assertIn("credentials issue", result["requests"][0]["human_help_request"])

    def test_help_center_resolve_transitions_to_human_resolved(self):
        task = Task(
            id="h2",
            title="Need resolve",
            description="blocked",
            source="manual",
            status=TaskStatus.NEEDS_HUMAN.value,
            priority=2,
            human_help_request="Please fix flaky external service.",
        )
        self.store.insert_task(task)

        result = _api_resolve_help_request(self.store, {"task_id": "h2", "resolution": "Service restored"})
        self.assertEqual(result["status"], "ok")

        updated = self.store.get_task("h2")
        self.assertEqual(updated.status, TaskStatus.HUMAN_RESOLVED.value)
        self.assertEqual(updated.human_help_request, "")

        events = self.store.get_events("h2")
        self.assertTrue(any(e["event_type"] == "human_resolved" for e in events))

    def test_experiences_returns_recent_entries(self):
        self.exp_store.add(
            Experience(
                id="exp1",
                task_id="t1",
                category="insight",
                summary="Always check task status transitions.",
                detail="A missing transition can stall the queue.",
                confidence=0.9,
            )
        )
        result = _api_experiences(self.exp_store, limit=10, category="", query="")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["experiences"][0]["id"], "exp1")
        self.assertEqual(result["experiences"][0]["category"], "insight")

    def test_register_model_api_persists_model(self):
        payload = _api_register_model(
            self.model_store,
            {
                "model_type": ModelType.LLM.value,
                "base_url": "https://example.com/v1",
                "model_name": "planner-model",
                "api_key": "secret-ak",
                "desc": "Primary planner model",
            },
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["model"]["model_name"], "planner-model")
        self.assertEqual(payload["model"]["api_key_preview"], "se***ak")
        self.assertEqual(payload["model"]["desc"], "Primary planner model")

    def test_register_embedding_model_api_persists_api_path(self):
        payload = _api_register_model(
            self.model_store,
            {
                "model_type": ModelType.EMBEDDING.value,
                "api_path": "https://ark.example.com/api/v3/embeddings/multimodal",
                "model_name": "embed-model",
                "api_key": "embed-ak",
                "desc": "Multimodal embedding endpoint",
            },
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["model"]["model_type"], ModelType.EMBEDDING.value)
        self.assertEqual(
            payload["model"]["api_path"],
            "https://ark.example.com/api/v3/embeddings/multimodal",
        )
        self.assertEqual(payload["model"]["base_url"], "")

    def test_bootstrap_status_requires_setup_without_default_llm(self):
        payload = _api_bootstrap_status(self.model_store)

        self.assertFalse(payload["ready"])
        self.assertTrue(payload["requires_setup"])
        self.assertIn("default_llm", payload["missing"])

    def test_models_api_returns_models_and_binding_points(self):
        model = self.model_store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="planner-model",
            api_key="secret-ak",
            desc="Primary planner model",
        )
        self.model_store.set_binding(ModelBindingPoint.EXECUTION.value, model.id)

        payload = _api_models(self.model_store)

        self.assertEqual(len(payload["models"]), 1)
        self.assertEqual(payload["bindings"][ModelBindingPoint.EXECUTION.value]["model_id"], model.id)
        self.assertTrue(any(item["binding_point"] == ModelBindingPoint.EXECUTION.value for item in payload["binding_points"]))

    def test_models_api_includes_effective_default_model_for_binding_points(self):
        model = self.model_store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="planner-model",
            api_key="secret-ak",
            desc="Primary planner model",
        )

        payload = _api_models(self.model_store)
        execution_binding = next(
            item for item in payload["binding_points"] if item["binding_point"] == ModelBindingPoint.EXECUTION.value
        )

        self.assertEqual(execution_binding["default_model_id"], model.id)
        self.assertEqual(execution_binding["default_model_name"], "planner-model")

    def test_models_api_returns_empty_default_model_when_none_exists(self):
        payload = _api_models(self.model_store)
        execution_binding = next(
            item for item in payload["binding_points"] if item["binding_point"] == ModelBindingPoint.EXECUTION.value
        )

        self.assertEqual(execution_binding["default_model_id"], "")
        self.assertEqual(execution_binding["default_model_name"], "")

    def test_models_api_includes_connection_status(self):
        self.model_store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="planner-model",
            api_key="secret-ak",
            desc="Primary planner model",
        )

        payload = _api_models(
            self.model_store,
            connection_status_provider=lambda _model: {
                "connection_status": "success",
                "connection_message": "Connection OK",
                "connection_checked_at": "2026-03-06T00:00:00+00:00",
            },
        )

        self.assertEqual(payload["models"][0]["connection_status"], "success")
        self.assertEqual(payload["models"][0]["connection_message"], "Connection OK")

    def test_set_model_bindings_api_updates_binding(self):
        model = self.model_store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="planner-model",
            api_key="secret-ak",
            desc="Primary planner model",
        )

        payload = _api_set_model_bindings(
            self.model_store,
            {"bindings": {ModelBindingPoint.EXECUTION.value: model.id}},
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["bindings"][ModelBindingPoint.EXECUTION.value]["model_id"], model.id)

    def test_set_default_model_api_updates_effective_default(self):
        model = self.model_store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="planner-model",
            api_key="secret-ak",
            desc="Primary planner model",
        )

        payload = _api_default_model(self.model_store, model.id)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["default_model"]["id"], model.id)
        self.assertEqual(self.model_store.get_default_model(ModelType.LLM.value).id, model.id)

    def test_update_model_api_updates_existing_model(self):
        model = self.model_store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="planner-model",
            api_key="secret-ak",
            desc="Primary planner model",
        )

        payload = _api_update_model(
            self.model_store,
            model.id,
            {
                "model_type": ModelType.LLM.value,
                "base_url": "https://example.com/v2",
                "model_name": "planner-model-v2",
                "api_key": "",
                "desc": "Updated planner model",
            },
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["model"]["id"], model.id)
        self.assertEqual(payload["model"]["base_url"], "https://example.com/v2")
        self.assertEqual(payload["model"]["model_name"], "planner-model-v2")
        self.assertEqual(payload["model"]["desc"], "Updated planner model")
        self.assertEqual(payload["model"]["api_key_preview"], "se***ak")

    def test_delete_model_api_removes_model_and_bindings(self):
        model = self.model_store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="planner-model",
            api_key="secret-ak",
            desc="Primary planner model",
        )
        self.model_store.set_binding(ModelBindingPoint.EXECUTION.value, model.id)

        payload = _api_delete_model(self.model_store, model.id)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["model_id"], model.id)
        self.assertIsNone(self.model_store.get_model(model.id))
        self.assertIsNone(self.model_store.get_binding(ModelBindingPoint.EXECUTION.value))

    def test_discovery_api_supports_new_event_envelope(self):
        activity_path = Path(self.tmp.name) / "activity.jsonl"
        activity_path.write_text(
            "\n".join([
                json.dumps({
                    "module": "Discovery",
                    "family": "strategy",
                    "event_name": "strategy_selected",
                    "detail": "change_hotspot │ queue=0",
                    "reasoning": "Prefer neglected areas",
                }),
                json.dumps({
                    "module": "Discovery",
                    "family": "candidate",
                    "event_name": "candidate_found",
                    "task_id": "t1",
                    "detail": "[todo] Fix stale TODO",
                    "data": {"candidate_id": "cand-1", "source": "todo_scan"},
                }),
                json.dumps({
                    "module": "Discovery",
                    "family": "valuation",
                    "event_name": "candidate_scored",
                    "task_id": "t1",
                    "detail": "score=0.820 rec=execute │ Fix stale TODO",
                    "reasoning": "[heuristic] impact=0.80",
                    "data": {"candidate_id": "cand-1", "score": 0.82},
                }),
                json.dumps({
                    "module": "Discovery",
                    "family": "valuation",
                    "event_name": "candidate_filtered_out",
                    "task_id": "t2",
                    "detail": "score=0.120 │ Minor cleanup",
                    "reasoning": "heuristic score too low",
                    "data": {"candidate_id": "cand-2", "score": 0.12},
                }),
                json.dumps({
                    "module": "Discovery",
                    "family": "queue",
                    "event_name": "candidate_queued",
                    "task_id": "t1",
                    "detail": "Fix stale TODO (source=todo_scan)",
                    "data": {"candidate_id": "cand-1", "source": "todo_scan"},
                }),
                json.dumps({
                    "module": "Discovery",
                    "family": "funnel",
                    "event_name": "funnel_summarized",
                    "detail": "raw=2 → heuristic=1 → llm=1 → final=1",
                    "data": {"raw_candidates": 2, "queued": 1},
                }),
            ]) + "\n",
            encoding="utf-8",
        )

        payload = _api_discovery(Path(self.tmp.name), limit=10)

        self.assertEqual(payload["strategy"]["action"], "strategy_selected")
        self.assertEqual(payload["strategy"]["event_name"], "strategy_selected")
        self.assertEqual(payload["latest_funnel"]["action"], "funnel_summarized")
        self.assertEqual(payload["latest_funnel"]["event_name"], "funnel_summarized")
        self.assertEqual(len(payload["candidates"]), 1)
        self.assertEqual(len(payload["scored"]), 1)
        self.assertEqual(len(payload["filtered_out"]), 1)
        self.assertEqual(len(payload["queued"]), 1)
        self.assertEqual(payload["counts"]["queued"], 1)

    def test_discovery_api_enriches_queued_events_with_task_trace(self):
        correlated_store = TaskStore(Path(self.tmp.name) / "tasks.db")
        self.addCleanup(correlated_store.close)
        correlated_store.insert_task(Task(
            id="t1",
            title="Fix stale TODO",
            description="Clean up lingering TODO in parser",
            source="todo_scan",
            status=TaskStatus.QUEUED.value,
            priority=2,
            execution_trace="reactloop: step 1 -> inspect\nreactloop: step 2 -> patch",
            branch_name="codex/fix-stale-todo",
        ))

        activity_path = Path(self.tmp.name) / "activity.jsonl"
        activity_path.write_text(
            json.dumps({
                "module": "Discovery",
                "family": "queue",
                "event_name": "candidate_queued",
                "task_id": "t1",
                "detail": "Fix stale TODO (source=todo_scan)",
                "data": {"source": "todo_scan", "title": "Fix stale TODO"},
            }) + "\n",
            encoding="utf-8",
        )

        payload = _api_discovery(Path(self.tmp.name), limit=10)

        self.assertEqual(len(payload["queued"]), 1)
        self.assertIn("task", payload["queued"][0])
        self.assertEqual(payload["queued"][0]["task"]["id"], "t1")
        self.assertIn("reactloop: step 1", payload["queued"][0]["task"]["execution_trace"])
        self.assertEqual(payload["queued"][0]["task"]["branch_name"], "codex/fix-stale-todo")


class TestPauseResumeAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directive_path = Path(self.tmp.name) / "directive.json"
        save_directive(self.directive_path, Directive())

    def tearDown(self):
        self.tmp.cleanup()

    def test_pause_sets_paused_true(self):
        result = _api_set_paused(self.directive_path, paused=True)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["paused"])
        self.assertTrue(load_directive(self.directive_path).paused)

    def test_resume_sets_paused_false(self):
        save_directive(self.directive_path, Directive(paused=True))
        result = _api_set_paused(self.directive_path, paused=False)
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["paused"])
        self.assertFalse(load_directive(self.directive_path).paused)

    def test_pause_preserves_other_fields(self):
        directive = load_directive(self.directive_path)
        directive.focus_areas = ["security", "testing"]
        directive.poll_interval_seconds = 60
        save_directive(self.directive_path, directive)

        _api_set_paused(self.directive_path, paused=True)
        reloaded = load_directive(self.directive_path)
        self.assertTrue(reloaded.paused)
        self.assertEqual(reloaded.focus_areas, ["security", "testing"])
        self.assertEqual(reloaded.poll_interval_seconds, 60)


class TestTaskDetailAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        self.store = TaskStore(self.db_path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_task_detail_returns_full_data(self):
        long_trace = '[{"tool": "read_file", "success": true}]' * 20
        long_log = "step result\n" * 200
        self.store.insert_task(Task(
            id="full1", title="Full Detail Task", description="desc",
            source="manual", status="completed", priority=2,
            execution_trace=long_trace, execution_log=long_log,
            token_cost=12345, time_cost_seconds=67.8,
            whats_learned="[pattern] Always validate input\n[pitfall] Don't skip tests",
        ))
        result = _api_task_detail(self.store, "full1")
        t = result["task"]
        self.assertEqual(t["execution_trace"], long_trace)
        self.assertEqual(t["execution_log"], long_log)
        self.assertEqual(t["token_cost"], 12345)
        self.assertEqual(t["time_cost_seconds"], 67.8)
        self.assertIn("Always validate input", t["whats_learned"])
        self.assertIn("cycle_id", t)

    def test_task_detail_includes_pr_status_metadata(self):
        self.store.insert_task(Task(
            id="full-pr",
            title="Task with linked PR",
            description="desc",
            source="manual",
            status="completed",
            priority=2,
            pr_url="https://github.com/Fullstop000/sprout/pull/77",
        ))

        result = _api_task_detail(
            self.store,
            "full-pr",
            pr_status_resolver=lambda _url: {
                "pr_number": 77,
                "pr_status": "open",
                "pr_title": "Show PR status",
            },
        )

        self.assertEqual(result["task"]["pr_number"], 77)
        self.assertEqual(result["task"]["pr_status"], "open")
        self.assertEqual(result["task"]["pr_title"], "Show PR status")

    def test_task_detail_not_found(self):
        result = _api_task_detail(self.store, "nonexistent")
        self.assertIn("error", result)

    def test_task_row_truncates(self):
        long_trace = "x" * 2000
        long_log = "y" * 2000
        t = Task(
            id="t1", title="T", description="D", source="s",
            status="queued", priority=2,
            execution_trace=long_trace, execution_log=long_log,
            token_cost=999, time_cost_seconds=12.5,
            whats_learned="z" * 500,
        )
        row = _task_row(t)
        self.assertEqual(len(row["execution_trace"]), 500)
        self.assertEqual(len(row["execution_log"]), 500)
        self.assertEqual(len(row["whats_learned"]), 200)
        self.assertEqual(row["token_cost"], 999)
        self.assertEqual(row["time_cost_seconds"], 12.5)

    def test_task_full_no_truncation(self):
        long_trace = "x" * 2000
        t = Task(
            id="t1", title="T", description="D", source="s",
            status="queued", priority=2,
            execution_trace=long_trace, token_cost=1000, time_cost_seconds=5.0,
            whats_learned="learned stuff",
        )
        full = _task_full(t)
        self.assertEqual(len(full["execution_trace"]), 2000)
        self.assertEqual(full["token_cost"], 1000)
        self.assertEqual(full["whats_learned"], "learned stuff")

    def test_task_detail_includes_events(self):
        self.store.insert_task(Task(
            id="ev1", title="Event Task", description="d",
            source="manual", status="queued", priority=2,
        ))
        self.store.add_event("ev1", "plan.started", "Planning began")
        self.store.add_event("ev1", "execute.step", "Edited file")
        result = _api_task_detail(self.store, "ev1")
        self.assertEqual(len(result["events"]), 2)

    def test_task_detail_with_thread_store_linked(self):
        """_api_task_detail must not access removed Thread attributes."""
        self.store.insert_task(Task(
            id="ts1", title="Blocked Task", description="d",
            source="manual", status="needs_human", priority=2,
        ))
        thread_store = ThreadStore(Path(self.tmp.name) / "threads.db")
        try:
            thread = thread_store.create_thread(title="Blocked Task", created_by="agent", body="Need help")
            thread_store.link_task(thread.id, "ts1")
            result = _api_task_detail(self.store, "ts1", thread_store=thread_store)
            self.assertIn("task", result)
            self.assertIn("thread", result)
            thread_data = result["thread"]
            self.assertEqual(thread_data["id"], thread.id)
            self.assertEqual(thread_data["status"], "open")
            self.assertNotIn("github_issue_number", thread_data)
            self.assertIsInstance(thread_data["messages"], list)
        finally:
            thread_store.close()

    def test_task_detail_with_thread_store_no_link(self):
        """Result must not include 'thread' key when no thread is linked."""
        self.store.insert_task(Task(
            id="ts2", title="Unlinked Task", description="d",
            source="manual", status="queued", priority=2,
        ))
        thread_store = ThreadStore(Path(self.tmp.name) / "threads2.db")
        try:
            result = _api_task_detail(self.store, "ts2", thread_store=thread_store)
            self.assertNotIn("thread", result)
        finally:
            thread_store.close()


class TestDashboardServer(unittest.TestCase):
    def test_server_starts_and_serves(self):
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "test.db"
        store = TaskStore(db_path)
        directive_path = Path(tmp.name) / "directive.json"
        save_directive(directive_path, Directive())

        port = 18787

        def run_server():
            serve_dashboard(store, directive_path, host="127.0.0.1", port=port)

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        time.sleep(0.5)

        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
            html = resp.read().decode()
            self.assertIn("Sprout Agent V2", html)
            if "/assets/dashboard.js" in html:
                self.assertIn("id=\"root\"", html)
                js_resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/assets/dashboard.js")
                js_body = js_resp.read().decode()
                self.assertGreater(len(js_body), 100)
            else:
                self.assertIn("Dashboard frontend build not found.", html)

            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/tasks")
            data = json.loads(resp.read().decode())
            self.assertIn("tasks", data)

            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/stats")
            data = json.loads(resp.read().decode())
            self.assertIn("total_tasks", data)
        finally:
            store.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import logging
import mimetypes
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

from llm247_v2.core.directive import load_directive, save_directive
from llm247_v2.core.models import Directive, TaskSourceConfig, TaskStatus
from llm247_v2.llm.client import probe_registered_model_connection
from llm247_v2.observability.catalog import decode_discovery_event
from llm247_v2.storage.model_registry import MODEL_BINDING_SPECS, ModelRegistryStore
from llm247_v2.storage.experience import ExperienceStore
from llm247_v2.storage.store import TaskStore

logger = logging.getLogger("llm247_v2.dashboard.server")
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND_DIST_DIR = _REPO_ROOT / "frontend" / "dist"


class ModelConnectionChecker:
    """Cache model connection probes so the dashboard can show recent status."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 30.0,
        probe_func: Callable[..., tuple[bool, str]] = probe_registered_model_connection,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._probe_func = probe_func
        self._lock = threading.Lock()
        self._cache: dict[str, dict[str, object]] = {}

    def get_status(self, model) -> dict[str, str]:
        """Return cached or freshly probed connectivity for one registered model."""
        cache_key = model.id
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and cached.get("updated_at") == model.updated_at:
                checked_monotonic = float(cached.get("checked_monotonic", 0.0))
                if time.monotonic() - checked_monotonic <= self._ttl_seconds:
                    return dict(cached["payload"])

        success, message = self._probe_func(model)
        payload = {
            "connection_status": "success" if success else "fail",
            "connection_message": message,
            "connection_checked_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._cache[cache_key] = {
                "updated_at": model.updated_at,
                "checked_monotonic": time.monotonic(),
                "payload": payload,
            }
        return dict(payload)


def serve_dashboard(
    store: TaskStore,
    directive_path: Path,
    host: str = "127.0.0.1",
    port: int = 8787,
    state_dir: Optional[Path] = None,
    experience_store: Optional[ExperienceStore] = None,
    model_store: Optional[ModelRegistryStore] = None,
    bootstrap_status_provider: Optional[Callable[[], dict]] = None,
    thread_store=None,
) -> None:
    """Start HTTP control plane server."""
    _state_dir = state_dir or directive_path.parent
    connection_checker = ModelConnectionChecker()

    class Handler(BaseHTTPRequestHandler):

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path == "/api/tasks":
                self._serve_json(_api_tasks(store))
            elif path.startswith("/api/tasks/"):
                task_id = path.split("/api/tasks/")[1].split("?")[0]
                self._serve_json(_api_task_detail(store, task_id, thread_store=thread_store))
            elif path == "/api/threads":
                status_filter = qs.get("status", [""])[0]
                self._serve_json(_api_threads(thread_store, status=status_filter or None))
            elif path.startswith("/api/threads/"):
                thread_id = path.split("/api/threads/")[1].split("?")[0]
                self._serve_json(_api_thread_detail(thread_store, thread_id))
            elif path == "/api/cycles":
                self._serve_json(_api_cycles(store))
            elif path == "/api/stats":
                self._serve_json(_api_stats(store))
            elif path == "/api/summary":
                self._serve_json(_api_summary(
                    store,
                    directive_path,
                    _state_dir,
                    model_store=model_store,
                    bootstrap_status_provider=bootstrap_status_provider,
                    thread_store=thread_store,
                ))
            elif path == "/api/help-center":
                self._serve_json(_api_help_center(store))
            elif path == "/api/experiences":
                limit = int(qs.get("limit", ["100"])[0])
                category = qs.get("category", [""])[0]
                query = qs.get("q", [""])[0]
                self._serve_json(_api_experiences(experience_store, limit=limit, category=category, query=query))
            elif path == "/api/directive":
                self._serve_json(_api_get_directive(directive_path))
            elif path == "/api/models":
                self._serve_json(_api_models(model_store, connection_status_provider=connection_checker.get_status))
            elif path == "/api/bootstrap-status":
                self._serve_json(_api_bootstrap_status(model_store, bootstrap_status_provider))
            elif path == "/api/activity":
                limit = int(qs.get("limit", ["200"])[0])
                module = qs.get("module", [""])[0]
                self._serve_json(_api_activity(_state_dir, limit, module))
            elif path == "/api/discovery":
                limit = int(qs.get("limit", ["50"])[0])
                self._serve_json(_api_discovery(_state_dir, limit))
            elif path == "/api/llm-audit":
                limit = int(qs.get("limit", ["50"])[0])
                seq_after = int(qs.get("seq_after", ["0"])[0])
                self._serve_json(_api_llm_audit(_state_dir, limit, seq_after))
            elif path.startswith("/api/llm-audit/"):
                seq = int(path.split("/api/llm-audit/")[1].split("?")[0])
                self._serve_json(_api_llm_audit_detail(_state_dir, seq))
            elif path == "/" or path == "/index.html":
                self._serve_html()
            elif path.startswith("/assets/") or path in {"/favicon.ico", "/manifest.webmanifest"}:
                self._serve_frontend_asset(path)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if self.path == "/api/directive":
                body = self._read_body()
                self._serve_json(_api_set_directive(directive_path, body))
            elif self.path.startswith("/api/models/") and self.path.endswith("/default"):
                model_id = self.path.split("/api/models/")[1].split("/default")[0]
                self._serve_json(_api_default_model(model_store, model_id))
            elif self.path == "/api/models":
                body = self._read_body()
                self._serve_json(_api_register_model(model_store, body))
            elif self.path == "/api/model-bindings":
                body = self._read_body()
                self._serve_json(_api_set_model_bindings(model_store, body))
            elif self.path == "/api/pause":
                self._serve_json(_api_set_paused(directive_path, paused=True))
            elif self.path == "/api/resume":
                self._serve_json(_api_set_paused(directive_path, paused=False))
            elif self.path == "/api/tasks/cancel":
                body = self._read_body()
                self._serve_json(_api_cancel_task(store, body))
            elif self.path == "/api/tasks/inject":
                body = self._read_body()
                self._serve_json(_api_inject_task(store, body))
            elif self.path == "/api/help-center/resolve":
                body = self._read_body()
                self._serve_json(_api_resolve_help_request(store, body))
            elif self.path.startswith("/api/threads/") and self.path.endswith("/reply"):
                thread_id = self.path.split("/api/threads/")[1].split("/reply")[0]
                body = self._read_body()
                self._serve_json(_api_thread_reply(thread_store, store, thread_id, body))
            elif self.path.startswith("/api/threads/") and self.path.endswith("/close"):
                thread_id = self.path.split("/api/threads/")[1].split("/close")[0]
                body = self._read_body()
                self._serve_json(_api_close_thread(thread_store, store, thread_id, body))
            elif self.path == "/api/threads":
                body = self._read_body()
                self._serve_json(_api_create_thread(thread_store, store, body))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_PUT(self) -> None:
            if self.path.startswith("/api/models/"):
                model_id = self.path.split("/api/models/")[1].split("?")[0]
                body = self._read_body()
                self._serve_json(_api_update_model(model_store, model_id, body))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_DELETE(self) -> None:
            if self.path.startswith("/api/models/"):
                model_id = self.path.split("/api/models/")[1].split("?")[0]
                self._serve_json(_api_delete_model(model_store, model_id))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def _serve_html(self) -> None:
            html = _dashboard_html().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def _serve_frontend_asset(self, request_path: str) -> None:
            """Serve dashboard frontend build artifacts from Vite dist output."""
            asset_path = _resolve_frontend_asset_path(request_path)
            if not asset_path:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            try:
                body = asset_path.read_bytes()
            except OSError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            content_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_json(self, data: Any) -> None:
            body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return {}

        def log_message(self, fmt: str, *args: object) -> None:
            logger.debug(fmt, *args)

    server = ThreadingHTTPServer((host, port), Handler)
    logger.info("Dashboard at http://%s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Dashboard shutting down")
    finally:
        server.shutdown()
        server.server_close()


def _api_tasks(store: TaskStore) -> dict:
    tasks = store.list_tasks(limit=200)
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tasks": [_task_row(t) for t in tasks],
    }


def _api_task_detail(store: TaskStore, task_id: str, *, thread_store=None) -> dict:
    task = store.get_task(task_id)
    if not task:
        return {"error": "task not found"}
    events = store.get_events(task_id)
    result: dict = {"task": _task_full(task), "events": events}
    if thread_store:
        thread = thread_store.get_thread_for_task(task_id)
        if thread:
            result["thread"] = {
                "id": thread.id,
                "status": thread.status,
                "messages": [
                    {"role": m.role, "body": m.body, "created_at": m.created_at}
                    for m in thread_store.get_messages(thread.id)
                ],
            }
    return result


def _api_cycles(store: TaskStore) -> dict:
    cycles = store.get_recent_cycles(limit=50)
    return {
        "cycles": [
            {
                "id": c.cycle_id, "started_at": c.started_at,
                "completed_at": c.completed_at, "status": c.status,
                "discovered": c.tasks_discovered, "executed": c.tasks_executed,
                "completed": c.tasks_completed, "failed": c.tasks_failed,
                "summary": c.summary,
            }
            for c in cycles
        ]
    }


def _api_stats(store: TaskStore) -> dict:
    return store.get_stats()


def _api_summary(
    store: TaskStore,
    directive_path: Path,
    state_dir: Path,
    *,
    model_store: Optional[ModelRegistryStore] = None,
    bootstrap_status_provider: Optional[Callable[[], dict]] = None,
    thread_store=None,
) -> dict:
    tasks = store.list_tasks(limit=200)
    task_rows = [_task_row(task) for task in tasks]
    stats = _api_stats(store)
    directive = _api_get_directive(directive_path)
    bootstrap = _api_bootstrap_status(model_store, bootstrap_status_provider)
    cycles = _api_cycles(store)["cycles"]
    help_requests = _api_help_center(store)["requests"]
    activity = _api_activity(state_dir, 120, "")["events"]
    threads = _api_threads(thread_store)["threads"] if thread_store is not None else []
    waiting_threads = [thread for thread in threads if thread.get("status") == "waiting_reply"]
    recent_completions = len([task for task in task_rows if task.get("status") in {"completed", "human_resolved"}])
    blocker_count = len(help_requests) + (1 if bootstrap.get("requires_setup") else 0)
    active_task = next((task for task in task_rows if task.get("status") in {"running", "executing", "planning"}), None)
    latest_cycle = cycles[0] if cycles else None
    updated_at = (
        next((e.get("timestamp") or e.get("ts") for e in reversed(activity) if e.get("timestamp") or e.get("ts")), "")
        or (threads[0].get("updated_at") if threads else "")
        or (task_rows[0].get("updated_at") if task_rows else "")
        or (latest_cycle.get("completed_at") if latest_cycle else "")
        or datetime.now(timezone.utc).isoformat()
    )

    summary_parts = [
        (
            f"The agent recently closed {recent_completions} task"
            f"{'' if recent_completions == 1 else 's'}."
            if recent_completions > 0
            else "No recent completions are visible yet."
        ),
        (
            f"It is currently focused on \"{active_task.get('title', '')}\"."
            if active_task
            else "It is not actively executing a task right now."
        ),
        (
            f"{blocker_count + len(waiting_threads)} item"
            f"{'' if blocker_count + len(waiting_threads) == 1 else 's'} may need operator attention."
            if blocker_count + len(waiting_threads) > 0
            else "There are no visible operator queues waiting right now."
        ),
    ]

    notes = [
        "Runtime is paused by directive." if directive.get("paused") else "Runtime is polling normally.",
        bootstrap.get("message", "Bootstrap status unavailable."),
        (
            f"Latest cycle #{latest_cycle.get('id')}: "
            f"{latest_cycle.get('discovered', 0)} discovered, "
            f"{latest_cycle.get('executed', 0)} executed, "
            f"{latest_cycle.get('failed', 0)} failed."
            if latest_cycle
            else "No cycle summary is available yet."
        ),
    ]

    task_title_by_id = {task["id"]: task.get("title") or f"Task {task['id'][:8]}" for task in task_rows}

    def build_change(event: dict) -> Optional[dict]:
        event_name = str(event.get("event_name", ""))
        task_id = str(event.get("task_id", ""))
        timestamp = str(event.get("timestamp") or event.get("ts") or "")
        detail = str(event.get("detail") or event.get("message") or "")
        reasoning = str(event.get("reasoning") or "")
        cycle_id = event.get("cycle_id")
        related_parts = []
        if task_id:
          related_parts.append(f"task {task_id[:8]}")
        if cycle_id:
          related_parts.append(f"cycle-{cycle_id}")
        related = " · ".join(related_parts) or "Execution state change"
        task_title = task_title_by_id.get(task_id, f"Task {task_id[:8]}") if task_id else ""

        if event_name == "task_completed" and task_id:
            return {
                "id": f"{event_name}-{task_id}-{timestamp}",
                "label": "Completed",
                "title": task_title,
                "why": reasoning or "This work finished successfully and may unlock follow-up tasks.",
                "timestamp": timestamp,
                "meta": related,
                "tone": "success",
                "action": {"kind": "task", "label": "Open task", "taskId": task_id},
            }
        if event_name in {"task_failed", "task_needs_human"} and task_id:
            return {
                "id": f"{event_name}-{task_id}-{timestamp}",
                "label": "Needs review" if event_name == "task_needs_human" else "Failed",
                "title": task_title,
                "why": reasoning or detail or "This task needs inspection before progress continues.",
                "timestamp": timestamp,
                "meta": related,
                "tone": "warning",
                "action": {"kind": "task", "label": "Review task", "taskId": task_id},
            }
        if event_name == "verification_completed" and event.get("success") is False and task_id:
            return {
                "id": f"{event_name}-{task_id}-{timestamp}",
                "label": "Verification",
                "title": task_title,
                "why": reasoning or detail or "Verification did not pass and the evidence trail needs review.",
                "timestamp": timestamp,
                "meta": related,
                "tone": "warning",
                "action": {"kind": "task", "label": "Open verification", "taskId": task_id},
            }
        if event_name == "candidate_queued":
            candidate_title = str(((event.get("data") or {}) if isinstance(event.get("data"), dict) else {}).get("title") or detail or "Discovery candidate queued")
            return {
                "id": f"{event_name}-{task_id or candidate_title}-{timestamp}",
                "label": "Discovery",
                "title": candidate_title,
                "why": reasoning or "The agent promoted a discovered opportunity into the task queue.",
                "timestamp": timestamp,
                "meta": related if related != "Execution state change" else "Discovery queue update",
                "tone": "default",
                "action": {"kind": "page", "label": "Open discovery", "page": "discovery"},
            }
        if event_name == "cycle_completed":
            return {
                "id": f"{event_name}-{timestamp}",
                "label": "Cycle",
                "title": detail or "Cycle completed",
                "why": reasoning or "The latest agent cycle finished and its results are ready for review.",
                "timestamp": timestamp,
                "meta": related if related != "Execution state change" else "Cycle lifecycle",
                "tone": "default",
                "action": {"kind": "page", "label": "Open work", "page": "work"},
            }
        return None

    changes = []
    for event in reversed(activity):
        projected = build_change(event)
        if projected:
            changes.append(projected)
        if len(changes) >= 6:
            break

    attention = []
    if bootstrap.get("requires_setup"):
        attention.append({
            "id": "setup-required",
            "label": "Setup",
            "title": "Initialization still needs attention",
            "detail": bootstrap.get("message", "Initialization is incomplete."),
            "tone": "warning",
            "action": {"kind": "page", "label": "Open control", "page": "control"},
        })
    for task in help_requests[:2]:
        attention.append({
            "id": f"help-{task['id']}",
            "label": "Needs human",
            "title": task.get("title", task["id"]),
            "detail": task.get("human_help_request") or "This task is waiting for operator guidance.",
            "tone": "warning",
            "action": {"kind": "task", "label": "Review task", "taskId": task["id"]},
        })
    for thread in waiting_threads[:2]:
        attention.append({
            "id": f"thread-{thread['id']}",
            "label": "Inbox",
            "title": thread.get("title", thread["id"]),
            "detail": "A human-agent thread is waiting for a reply or acknowledgement.",
            "tone": "default",
            "action": {"kind": "thread", "label": "Open thread", "threadId": thread["id"]},
        })

    destinations = [
        {
            "page": "work",
            "label": "Work",
            "description": "Inspect tasks, execution traces, and cycle outcomes.",
            "countLabel": f"{len(task_rows):,} tasks",
        },
        {
            "page": "inbox",
            "label": "Inbox",
            "description": "Continue async conversation with the agent.",
            "countLabel": f"{len(waiting_threads):,} waiting",
        },
        {
            "page": "discovery",
            "label": "Discovery",
            "description": "Review newly queued opportunities and source signals.",
        },
        {
            "page": "memory",
            "label": "Memory & Audit",
            "description": "Read detailed evidence, activity, and LLM audit trails.",
        },
        {
            "page": "control",
            "label": "Control",
            "description": "Adjust models, directives, and manual interventions.",
            "countLabel": "setup pending" if bootstrap.get("requires_setup") else None,
        },
    ]

    return {
        "updated_at": updated_at,
        "briefing": {
            "eyebrow": "Review Briefing",
            "title": "What changed since you last looked",
            "summary": " ".join(summary_parts),
            "statusLine": "Paused for review" if directive.get("paused") else "Live and ready for async review",
            "updatedLabel": f"Updated {updated_at}",
            "metrics": [
                {"label": "Input tokens", "value": f"{int(stats.get('input_tokens') or 0):,}", "hint": "cumulative prompt volume"},
                {"label": "Output tokens", "value": f"{int(stats.get('output_tokens') or 0):,}", "hint": "cumulative model output"},
                {"label": "Recent completions", "value": f"{recent_completions:,}", "hint": "finished tasks in the current list"},
                {"label": "Current blockers", "value": f"{blocker_count:,}", "hint": "human or setup issues"},
            ],
            "notes": notes,
            "activeTask": active_task,
            "latestCycle": latest_cycle,
        },
        "changes": changes,
        "attention": attention,
        "destinations": destinations,
    }


def _api_help_center(store: TaskStore) -> dict:
    """List unresolved tasks that currently require human intervention."""
    tasks = store.list_human_help_tasks(limit=200)
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "requests": [_task_row(task) for task in tasks],
    }


def _api_resolve_help_request(store: TaskStore, body: dict) -> dict:
    """Resolve one human-help request and queue it for verification retry."""
    task_id = str(body.get("task_id", "")).strip()
    if not task_id:
        return {"error": "task_id required"}

    task = store.get_task(task_id)
    if not task:
        return {"error": "task not found"}
    if task.status != TaskStatus.NEEDS_HUMAN.value:
        return {"error": f"task status must be {TaskStatus.NEEDS_HUMAN.value}"}

    resolution = str(body.get("resolution", "")).strip()
    task.status = TaskStatus.HUMAN_RESOLVED.value
    task.human_help_request = ""
    store.update_task(task)
    detail = f"Resolved via dashboard. {resolution}".strip()
    store.add_event(task.id, "human_resolved", detail)
    return {"status": "ok", "task_id": task.id, "next_status": task.status}


def _api_experiences(
    experience_store: Optional[ExperienceStore],
    *,
    limit: int = 100,
    category: str = "",
    query: str = "",
) -> dict:
    """List experiences so dashboard can show long-term memory contents."""
    if experience_store is None:
        return {"experiences": [], "total": 0, "updated_at": datetime.now(timezone.utc).isoformat()}

    safe_limit = max(1, min(500, limit))
    if query:
        experiences = experience_store.search(query, limit=safe_limit)
    elif category:
        experiences = experience_store.get_by_category(category, limit=safe_limit)
    else:
        experiences = experience_store.get_recent(limit=safe_limit)

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(experiences),
        "experiences": [_experience_row(exp) for exp in experiences],
    }


def _api_get_directive(path: Path) -> dict:
    d = load_directive(path)
    sources = {}
    for k, v in d.task_sources.items():
        sources[k] = {"enabled": v.enabled, "priority": v.priority}
    return {
        "paused": d.paused,
        "focus_areas": d.focus_areas,
        "forbidden_paths": d.forbidden_paths,
        "max_file_changes_per_task": d.max_file_changes_per_task,
        "custom_instructions": d.custom_instructions,
        "task_sources": sources,
        "poll_interval_seconds": d.poll_interval_seconds,
    }


def _api_models(
    model_store: Optional[ModelRegistryStore],
    connection_status_provider: Optional[Callable[[object], dict[str, str]]] = None,
) -> dict:
    """List registered models, runtime bindings, and binding-point metadata."""
    models = model_store.list_models() if model_store else []
    bindings = model_store.list_bindings() if model_store else {}
    default_models_by_type = {
        spec.model_type: model_store.get_default_model(spec.model_type) if model_store else None
        for spec in MODEL_BINDING_SPECS
    }
    return {
        "models": [
            _registered_model_row(
                model,
                connection_status=connection_status_provider(model) if connection_status_provider else None,
            )
            for model in models
        ],
        "bindings": {
            binding_point: {
                "model_id": binding.model_id,
                "updated_at": binding.updated_at,
            }
            for binding_point, binding in bindings.items()
        },
        "binding_points": [
            {
                "binding_point": spec.binding_point,
                "label": spec.label,
                "description": spec.description,
                "model_type": spec.model_type,
                "default_model_id": default_models_by_type[spec.model_type].id if default_models_by_type[spec.model_type] else "",
                "default_model_name": default_models_by_type[spec.model_type].model_name if default_models_by_type[spec.model_type] else "",
            }
            for spec in MODEL_BINDING_SPECS
        ],
    }


def _api_bootstrap_status(
    model_store: Optional[ModelRegistryStore],
    bootstrap_status_provider: Optional[Callable[[], dict]] = None,
) -> dict:
    """Expose startup readiness so the dashboard can guide initialization."""
    if bootstrap_status_provider is not None:
        return bootstrap_status_provider()
    ready = model_store is not None and model_store.get_default_model() is not None
    missing = [] if ready else ["default_llm"]
    return {
        "ready": ready,
        "requires_setup": not ready,
        "missing": missing,
        "recommended_tab": "models",
        "message": (
            "Register at least one llm model in the Models page to finish initialization."
            if not ready
            else "Runtime prerequisites satisfied."
        ),
    }


def _api_register_model(model_store: Optional[ModelRegistryStore], body: dict) -> dict:
    """Register one model for later binding from the dashboard."""
    if model_store is None:
        return {"error": "model registry unavailable"}
    try:
        model = model_store.register_model(
            model_type=str(body.get("model_type", "")),
            base_url=str(body.get("base_url", "")),
            api_path=str(body.get("api_path", "")),
            model_name=str(body.get("model_name", "")),
            api_key=str(body.get("api_key", "")),
            desc=str(body.get("desc", "")),
            roocode_wrapper=bool(body.get("roocode_wrapper", False)),
        )
    except ValueError as exc:
        return {"error": str(exc)}
    return {"status": "ok", "model": _registered_model_row(model)}


def _api_update_model(model_store: Optional[ModelRegistryStore], model_id: str, body: dict) -> dict:
    """Update one registered model from dashboard edit actions."""
    if model_store is None:
        return {"error": "model registry unavailable"}
    try:
        model = model_store.update_model(
            model_id,
            model_type=str(body.get("model_type", "")),
            base_url=str(body.get("base_url", "")),
            api_path=str(body.get("api_path", "")),
            model_name=str(body.get("model_name", "")),
            api_key=str(body.get("api_key", "")),
            desc=str(body.get("desc", "")),
            roocode_wrapper=bool(body.get("roocode_wrapper", False)),
        )
    except ValueError as exc:
        return {"error": str(exc)}
    return {"status": "ok", "model": _registered_model_row(model)}


def _api_default_model(model_store: Optional[ModelRegistryStore], model_id: str) -> dict:
    """Persist one explicit default model selection."""
    if model_store is None:
        return {"error": "model registry unavailable"}
    try:
        model = model_store.set_default_model(model_id)
    except ValueError as exc:
        return {"error": str(exc)}
    return {"status": "ok", "default_model": _registered_model_row(model)}


def _api_delete_model(model_store: Optional[ModelRegistryStore], model_id: str) -> dict:
    """Delete one registered model and clear bindings that referenced it."""
    if model_store is None:
        return {"error": "model registry unavailable"}
    try:
        model_store.delete_model(model_id)
    except ValueError as exc:
        return {"error": str(exc)}
    return {"status": "ok", "model_id": model_id}


def _api_set_model_bindings(model_store: Optional[ModelRegistryStore], body: dict) -> dict:
    """Persist dashboard-selected runtime model bindings."""
    if model_store is None:
        return {"error": "model registry unavailable"}
    bindings = body.get("bindings", {})
    if not isinstance(bindings, dict):
        return {"error": "bindings must be an object"}
    try:
        for binding_point, model_id in bindings.items():
            model_store.set_binding(str(binding_point), str(model_id))
    except ValueError as exc:
        return {"error": str(exc)}
    return {"status": "ok", "bindings": _api_models(model_store)["bindings"]}


def _api_set_paused(path: Path, *, paused: bool) -> dict:
    """Toggle agent paused state without overwriting other directive fields."""
    directive = load_directive(path)
    directive.paused = paused
    save_directive(path, directive)
    return {"status": "ok", "paused": directive.paused}


def _api_set_directive(path: Path, body: dict) -> dict:
    sources: dict[str, TaskSourceConfig] = {}
    for k, v in body.get("task_sources", {}).items():
        if isinstance(v, dict):
            sources[k] = TaskSourceConfig(
                enabled=bool(v.get("enabled", True)),
                priority=int(v.get("priority", 3)),
            )

    directive = Directive(
        paused=bool(body.get("paused", False)),
        focus_areas=body.get("focus_areas", []),
        forbidden_paths=body.get("forbidden_paths", [".env", ".git"]),
        max_file_changes_per_task=int(body.get("max_file_changes_per_task", 10)),
        custom_instructions=str(body.get("custom_instructions", "")),
        task_sources=sources,
        poll_interval_seconds=int(body.get("poll_interval_seconds", 120)),
    )
    save_directive(path, directive)
    return {"status": "ok", "directive": _api_get_directive(path)}


def _api_cancel_task(store: TaskStore, body: dict) -> dict:
    task_id = body.get("task_id", "")
    task = store.get_task(task_id)
    if not task:
        return {"error": "task not found"}
    if task.status in (TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value):
        return {"error": f"task already {task.status}"}
    task.status = TaskStatus.CANCELLED.value
    store.update_task(task)
    store.add_event(task_id, "cancelled", "Cancelled via dashboard")
    return {"status": "ok"}


def _api_inject_task(store: TaskStore, body: dict) -> dict:
    import hashlib
    title = str(body.get("title", "")).strip()
    if not title:
        return {"error": "title required"}
    task_id = hashlib.sha256(f"manual:{title}".encode()).hexdigest()[:12]
    from llm247_v2.core.models import Task, TaskSource
    task = Task(
        id=task_id,
        title=title,
        description=str(body.get("description", "")),
        source=TaskSource.MANUAL.value,
        status=TaskStatus.QUEUED.value,
        priority=int(body.get("priority", 2)),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.insert_task(task)
    store.add_event(task_id, "injected", "Created via dashboard")
    return {"status": "ok", "task_id": task_id}


def _read_jsonl_tail(path: Path, limit: int) -> list[dict]:
    """Read the last *limit* lines from a JSONL file efficiently."""
    if not path.exists():
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return []
            chunk_size = min(size, max(limit * 600, 65536))
            f.seek(max(0, size - chunk_size))
            raw = f.read().decode("utf-8", errors="replace")
        lines = raw.strip().splitlines()[-limit:]
        results = []
        for line in lines:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return results
    except OSError:
        return []


def _api_activity(state_dir: Path, limit: int, module: str) -> dict:
    """Read the last N activity events from activity.jsonl."""
    path = state_dir / "activity.jsonl"
    fetch_limit = limit * 3 if module else limit
    entries = _read_jsonl_tail(path, fetch_limit)
    entries = [e for e in entries if e.get("module")]
    if module:
        entries = [e for e in entries if e.get("module") == module]
    entries = entries[-limit:]
    return {"events": entries, "total_returned": len(entries)}


def _api_discovery(state_dir: Path, limit: int) -> dict:
    """Project recent discovery-related observer events into one dashboard payload."""
    path = state_dir / "activity.jsonl"
    entries = _read_jsonl_tail(path, max(limit * 12, 240))
    discovery_events = [decoded for decoded in (decode_discovery_event(entry) for entry in entries) if decoded is not None]

    candidates = [e for e in discovery_events if e.get("event_name") == "candidate_found"][-limit:]
    queued = [e for e in discovery_events if e.get("event_name") == "candidate_queued"][-limit:]
    scored = [e for e in discovery_events if e.get("event_name") == "candidate_scored"][-limit:]
    filtered_out = [e for e in discovery_events if e.get("event_name") == "candidate_filtered_out"][-limit:]
    strategy = next((e for e in reversed(discovery_events) if e.get("event_name") == "strategy_selected"), None)
    funnel = next((e for e in reversed(discovery_events) if e.get("event_name") == "funnel_summarized"), None)
    queued_task_map = _load_task_rows_by_id(state_dir, [e.get("task_id", "") for e in queued])
    queued = [_attach_discovery_task(entry, queued_task_map) for entry in queued]

    return {
        "strategy": strategy,
        "latest_funnel": funnel,
        "candidates": candidates,
        "scored": scored,
        "filtered_out": filtered_out,
        "queued": queued,
        "counts": {
            "candidates": len(candidates),
            "scored": len(scored),
            "filtered_out": len(filtered_out),
            "queued": len(queued),
        },
    }


def _load_task_rows_by_id(state_dir: Path, task_ids: list[str]) -> Dict[str, Dict]:
    valid_ids = [task_id for task_id in task_ids if task_id]
    if not valid_ids:
        return {}

    db_path = state_dir / "tasks.db"
    if not db_path.exists():
        return {}

    store = TaskStore(db_path)
    try:
        task_rows: Dict[str, Dict] = {}
        for task_id in valid_ids:
            task = store.get_task(task_id)
            if task is not None:
                task_rows[task_id] = _task_full(task)
        return task_rows
    finally:
        store.close()


def _attach_discovery_task(entry: dict, task_rows: Dict[str, Dict]) -> dict:
    task_id = entry.get("task_id", "")
    if not task_id or task_id not in task_rows:
        return entry

    enriched = dict(entry)
    enriched["task"] = task_rows[task_id]
    return enriched


def _api_llm_audit(state_dir: Path, limit: int, seq_after: int) -> dict:
    """Read LLM audit entries from llm_audit.jsonl."""
    path = state_dir / "llm_audit.jsonl"
    entries = _read_jsonl_tail(path, limit * 2 if seq_after else limit)
    if seq_after:
        entries = [e for e in entries if e.get("seq", 0) > seq_after]
    entries = entries[-limit:]
    for e in entries:
        e.pop("prompt_full", None)
        e.pop("response_full", None)
    return {"entries": entries, "total_returned": len(entries)}


def _api_llm_audit_detail(state_dir: Path, seq: int) -> dict:
    """Read a single LLM audit entry with full prompt/response."""
    path = state_dir / "llm_audit.jsonl"
    entries = _read_jsonl_tail(path, 500)
    for e in entries:
        if e.get("seq") == seq:
            return {"entry": e}
    return {"error": "entry not found"}


def _resolve_frontend_asset_path(request_path: str) -> Optional[Path]:
    """Resolve safe frontend build artifact path under frontend/dist."""
    relative_path = request_path.lstrip("/")
    if not relative_path:
        return None
    candidate = (_FRONTEND_DIST_DIR / relative_path).resolve()
    dist_root = _FRONTEND_DIST_DIR.resolve()
    try:
        candidate.relative_to(dist_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _task_row(t) -> Dict:
    return {
        "id": t.id, "title": t.title, "description": t.description,
        "source": t.source, "status": t.status, "priority": t.priority,
        "created_at": t.created_at, "updated_at": t.updated_at,
        "branch_name": t.branch_name, "pr_url": t.pr_url,
        "execution_trace": t.execution_trace[:500] if t.execution_trace else "",
        "execution_log": t.execution_log[:500] if t.execution_log else "",
        "error_message": t.error_message,
        "prompt_token_cost": t.prompt_token_cost,
        "completion_token_cost": t.completion_token_cost,
        "token_cost": t.token_cost,
        "time_cost_seconds": t.time_cost_seconds,
        "whats_learned": t.whats_learned[:200] if t.whats_learned else "",
        "human_help_request": t.human_help_request[:500] if t.human_help_request else "",
    }


def _task_full(t) -> Dict:
    """Full task data without truncation — for detail view."""
    return {
        "id": t.id, "title": t.title, "description": t.description,
        "source": t.source, "status": t.status, "priority": t.priority,
        "created_at": t.created_at, "updated_at": t.updated_at,
        "branch_name": t.branch_name, "pr_url": t.pr_url,
        "execution_trace": t.execution_trace,
        "execution_log": t.execution_log,
        "error_message": t.error_message,
        "prompt_token_cost": t.prompt_token_cost,
        "completion_token_cost": t.completion_token_cost,
        "token_cost": t.token_cost,
        "time_cost_seconds": t.time_cost_seconds,
        "whats_learned": t.whats_learned,
        "human_help_request": t.human_help_request,
        "cycle_id": t.cycle_id,
    }


def _experience_row(exp) -> Dict:
    """Serialize one experience row for dashboard JSON responses."""
    return {
        "id": exp.id,
        "task_id": exp.task_id,
        "category": exp.category,
        "summary": exp.summary,
        "detail": exp.detail,
        "tags": exp.tags,
        "confidence": exp.confidence,
        "created_at": exp.created_at,
        "applied_count": exp.applied_count,
        "source_outcome": exp.source_outcome,
    }


def _registered_model_row(model, connection_status: Optional[dict[str, str]] = None) -> Dict:
    """Serialize one registered model without exposing the full API key."""
    row = {
        "id": model.id,
        "model_type": model.model_type,
        "base_url": model.base_url,
        "api_path": model.api_path,
        "model_name": model.model_name,
        "api_key_preview": _mask_api_key(model.api_key),
        "desc": model.desc,
        "roocode_wrapper": model.roocode_wrapper,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }
    if connection_status:
        row.update(connection_status)
    return row


def _mask_api_key(api_key: str) -> str:
    """Return a short preview for a secret without leaking the full value."""
    clean = str(api_key).strip()
    if len(clean) <= 4:
        return "*" * len(clean)
    return f"{clean[:2]}***{clean[-2:]}"


def _thread_row(thread) -> Dict:
    return {
        "id": thread.id,
        "title": thread.title,
        "status": thread.status,
        "created_by": thread.created_by,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
    }


def _api_threads(thread_store, status: Optional[str] = None) -> dict:
    if thread_store is None:
        return {"threads": [], "total": 0}
    threads = thread_store.list_threads(status=status, limit=200)
    return {"threads": [_thread_row(t) for t in threads], "total": len(threads)}


def _api_thread_detail(thread_store, thread_id: str) -> dict:
    if thread_store is None:
        return {"error": "thread store unavailable"}
    thread = thread_store.get_thread(thread_id)
    if not thread:
        return {"error": "thread not found"}
    messages = thread_store.get_messages(thread_id)
    task_ids = thread_store.get_tasks_for_thread(thread_id)
    return {
        "thread": _thread_row(thread),
        "messages": [
            {"id": m.id, "role": m.role, "body": m.body, "created_at": m.created_at}
            for m in messages
        ],
        "task_ids": task_ids,
    }


def _api_thread_reply(thread_store, store: TaskStore, thread_id: str, body: dict) -> dict:
    """Human posts a reply; marks thread as replied so agent picks it up next cycle."""
    if thread_store is None:
        return {"error": "thread store unavailable"}
    thread = thread_store.get_thread(thread_id)
    if not thread:
        return {"error": "thread not found"}
    if thread.status == "closed":
        return {"error": "thread is closed"}
    text = str(body.get("body", "")).strip()
    if not text:
        return {"error": "body required"}
    thread_store.add_message(thread_id, "human", text)
    thread_store.set_status(thread_id, "replied")
    return {"status": "ok", "thread_id": thread_id}


def _api_close_thread(thread_store, store: TaskStore, thread_id: str, body: dict) -> dict:
    """Human closes a thread; linked NEEDS_HUMAN / QUEUED tasks are moved to FAILED."""
    if thread_store is None:
        return {"error": "thread store unavailable"}
    thread = thread_store.get_thread(thread_id)
    if not thread:
        return {"error": "thread not found"}
    if thread.status == "closed":
        return {"error": "thread already closed"}
    reason = str(body.get("reason", "")).strip() or "Closed by human"
    thread_store.add_message(thread_id, "human", reason)
    thread_store.set_status(thread_id, "closed")
    cancellable = {TaskStatus.NEEDS_HUMAN.value, TaskStatus.QUEUED.value}
    for task_id in thread_store.get_tasks_for_thread(thread_id):
        task = store.get_task(task_id)
        if task and task.status in cancellable:
            task.status = TaskStatus.FAILED.value
            task.error_message = f"Cancelled by human: {reason}"
            store.update_task(task)
            store.add_event(task_id, "cancelled", f"Human closed thread: {reason}")
    return {"status": "ok", "thread_id": thread_id}


def _api_create_thread(thread_store, store: TaskStore, body: dict) -> dict:
    """Human opens a new thread (Shape B) — creates thread + queued task."""
    if thread_store is None:
        return {"error": "thread store unavailable"}
    title = str(body.get("title", "")).strip()
    if not title:
        return {"error": "title required"}
    description = str(body.get("description", "")).strip()
    import hashlib
    from llm247_v2.core.models import Task, TaskSource
    task_id = hashlib.sha256(f"inbox:{title}".encode()).hexdigest()[:12]
    task = Task(
        id=task_id,
        title=title,
        description=description,
        source=TaskSource.MANUAL.value,
        status=TaskStatus.QUEUED.value,
        priority=int(body.get("priority", 3)),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.insert_task(task)
    opening = description or title
    thread = thread_store.create_thread(title=title, created_by="human", body=opening)
    thread_store.link_task(thread.id, task_id)
    store.add_event(task_id, "injected", f"Created via Inbox (thread {thread.id})")
    return {"status": "ok", "thread_id": thread.id, "task_id": task_id}


def _dashboard_html() -> str:
    """Return Vite-built frontend HTML, with fallback when dist is missing."""
    index_html_path = _FRONTEND_DIST_DIR / "index.html"
    try:
        return index_html_path.read_text(encoding="utf-8")
    except OSError:
        return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sprout Agent V2 — Frontend Not Built</title>
</head>
<body>
  <h1>Sprout Agent V2</h1>
  <p>Dashboard frontend build not found.</p>
  <p>Run: <code>./scripts/start_v2.sh ui</code> (auto-builds frontend) </p>
  <p>Or build manually: <code>cd frontend && npm install && npm run build</code></p>
</body>
</html>"""

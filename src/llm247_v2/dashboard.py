from __future__ import annotations

import json
import logging
import mimetypes
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from llm247_v2.directive import load_directive, save_directive
from llm247_v2.models import Directive, TaskSourceConfig, TaskStatus
from llm247_v2.store import TaskStore

logger = logging.getLogger("llm247_v2.dashboard")
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_DIST_DIR = _REPO_ROOT / "frontend" / "dist"


def serve_dashboard(
    store: TaskStore,
    directive_path: Path,
    host: str = "127.0.0.1",
    port: int = 8787,
    state_dir: Optional[Path] = None,
) -> None:
    """Start HTTP control plane server."""
    _state_dir = state_dir or directive_path.parent

    class Handler(BaseHTTPRequestHandler):

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path == "/api/tasks":
                self._serve_json(_api_tasks(store))
            elif path.startswith("/api/tasks/"):
                task_id = path.split("/api/tasks/")[1].split("?")[0]
                self._serve_json(_api_task_detail(store, task_id))
            elif path == "/api/cycles":
                self._serve_json(_api_cycles(store))
            elif path == "/api/stats":
                self._serve_json(_api_stats(store))
            elif path == "/api/directive":
                self._serve_json(_api_get_directive(directive_path))
            elif path == "/api/activity":
                limit = int(qs.get("limit", ["200"])[0])
                phase = qs.get("phase", [""])[0]
                self._serve_json(_api_activity(_state_dir, limit, phase))
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


def _api_task_detail(store: TaskStore, task_id: str) -> dict:
    task = store.get_task(task_id)
    if not task:
        return {"error": "task not found"}
    events = store.get_events(task_id)
    return {"task": _task_full(task), "events": events}


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
    from llm247_v2.models import Task, TaskSource
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


def _api_activity(state_dir: Path, limit: int, phase: str) -> dict:
    """Read the last N activity events from activity.jsonl."""
    path = state_dir / "activity.jsonl"
    fetch_limit = limit * 3 if phase else limit
    entries = _read_jsonl_tail(path, fetch_limit)
    if phase:
        entries = [e for e in entries if e.get("phase") == phase]
    entries = entries[-limit:]
    return {"events": entries, "total_returned": len(entries)}


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
        "plan": t.plan[:500] if t.plan else "",
        "execution_log": t.execution_log[:500] if t.execution_log else "",
        "verification_result": t.verification_result,
        "error_message": t.error_message,
        "token_cost": t.token_cost,
        "time_cost_seconds": t.time_cost_seconds,
        "whats_learned": t.whats_learned[:200] if t.whats_learned else "",
    }


def _task_full(t) -> Dict:
    """Full task data without truncation — for detail view."""
    return {
        "id": t.id, "title": t.title, "description": t.description,
        "source": t.source, "status": t.status, "priority": t.priority,
        "created_at": t.created_at, "updated_at": t.updated_at,
        "branch_name": t.branch_name, "pr_url": t.pr_url,
        "plan": t.plan,
        "execution_log": t.execution_log,
        "verification_result": t.verification_result,
        "error_message": t.error_message,
        "token_cost": t.token_cost,
        "time_cost_seconds": t.time_cost_seconds,
        "whats_learned": t.whats_learned,
        "cycle_id": t.cycle_id,
    }


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
  <title>TokenBurn Agent V2 — Frontend Not Built</title>
</head>
<body>
  <h1>TokenBurn Agent V2</h1>
  <p>Dashboard frontend build not found.</p>
  <p>Run: <code>./scripts/start_v2.sh ui</code> (auto-builds frontend) </p>
  <p>Or build manually: <code>cd frontend && npm install && npm run build</code></p>
</body>
</html>"""

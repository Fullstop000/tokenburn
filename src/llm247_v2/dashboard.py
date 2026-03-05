from __future__ import annotations

import json
import logging
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

            if path == "/" or path == "/index.html":
                self._serve_html()
            elif path == "/api/tasks":
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
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if self.path == "/api/directive":
                body = self._read_body()
                self._serve_json(_api_set_directive(directive_path, body))
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
    return r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TokenBurn Agent V2 — Control Plane</title>
<style>
:root {
  --bg: #0a0e17; --surface: #111827; --border: #1e293b;
  --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8;
  --ok: #34d399; --warn: #fbbf24; --danger: #f87171;
  --radius: 10px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Inter","SF Pro",system-ui,sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
.app { max-width: 1400px; margin: 0 auto; padding: 20px; }
header { display: flex; justify-content: space-between; align-items: center; padding: 16px 0; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
header h1 { font-size: 22px; font-weight: 700; }
header .meta { font-size: 12px; color: var(--muted); font-family: monospace; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px,1fr)); gap: 12px; margin-bottom: 20px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; }
.card .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }
.card .value { font-size: 26px; font-weight: 700; margin-top: 4px; }
.tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.tab { padding: 6px 14px; border-radius: 6px; background: var(--surface); border: 1px solid var(--border); color: var(--muted); cursor: pointer; font-size: 13px; }
.tab.active { background: var(--accent); color: #000; border-color: var(--accent); font-weight: 600; }
.panel { display: none; }
.panel.active { display: block; }
table { width: 100%; border-collapse: collapse; background: var(--surface); border-radius: var(--radius); overflow: hidden; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
th { background: rgba(56,189,248,0.06); color: var(--accent); font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 11px; font-weight: 600; }
.badge-discovered { background: rgba(148,163,184,0.15); color: var(--muted); }
.badge-queued { background: rgba(251,191,36,0.12); color: var(--warn); }
.badge-planning,.badge-executing,.badge-verifying { background: rgba(56,189,248,0.12); color: var(--accent); }
.badge-completed { background: rgba(52,211,153,0.12); color: var(--ok); }
.badge-failed { background: rgba(248,113,113,0.12); color: var(--danger); }
.badge-cancelled { background: rgba(148,163,184,0.1); color: #64748b; }
.pr-link { color: var(--accent); text-decoration: none; }
.pr-link:hover { text-decoration: underline; }
.ctrl { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; margin-bottom: 16px; }
.ctrl h3 { font-size: 14px; margin-bottom: 12px; color: var(--accent); }
.ctrl label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; margin-top: 10px; }
.ctrl input, .ctrl textarea, .ctrl select { width: 100%; padding: 8px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text); font-size: 13px; }
.ctrl textarea { min-height: 60px; resize: vertical; }
.ctrl button, .btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; font-weight: 600; }
.btn-primary { background: var(--accent); color: #000; }
.btn-danger { background: var(--danger); color: #fff; }
.btn-ok { background: var(--ok); color: #000; }
.btn-sm { padding: 4px 10px; font-size: 11px; }
.row { display: flex; gap: 12px; flex-wrap: wrap; }
.row > * { flex: 1; min-width: 200px; }
.mono { font-family: "JetBrains Mono","Fira Code",monospace; font-size: 12px; }
pre { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 10px; overflow-x: auto; font-size: 12px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
.toast { position: fixed; bottom: 20px; right: 20px; padding: 10px 18px; border-radius: 8px; font-size: 13px; display: none; z-index: 99; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.toolbar select, .toolbar input { padding: 6px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text); font-size: 12px; }
.phase-tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; letter-spacing: .5px; text-transform: uppercase; }
.phase-cycle { background: rgba(255,255,255,0.08); color: #fff; }
.phase-discover { background: rgba(56,189,248,0.15); color: var(--accent); }
.phase-value { background: rgba(99,102,241,0.15); color: #818cf8; }
.phase-plan { background: rgba(251,191,36,0.15); color: var(--warn); }
.phase-execute { background: rgba(52,211,153,0.15); color: var(--ok); }
.phase-verify { background: rgba(52,211,153,0.15); color: var(--ok); }
.phase-git { background: rgba(56,189,248,0.15); color: var(--accent); }
.phase-system { background: rgba(248,113,113,0.15); color: var(--danger); }
.phase-decision { background: rgba(251,191,36,0.15); color: var(--warn); }
.log-row { display: flex; gap: 8px; padding: 5px 8px; border-bottom: 1px solid var(--border); font-size: 12px; align-items: baseline; }
.log-row:hover { background: rgba(56,189,248,0.04); }
.log-time { color: var(--muted); flex-shrink: 0; width: 70px; font-family: "JetBrains Mono",monospace; font-size: 11px; }
.log-phase { flex-shrink: 0; width: 80px; }
.log-action { color: var(--text); flex-shrink: 0; min-width: 120px; font-weight: 600; font-size: 12px; }
.log-detail { color: var(--muted); flex: 1; word-break: break-word; }
.log-task { color: var(--accent); font-family: monospace; font-size: 11px; flex-shrink: 0; cursor: pointer; }
.log-task:hover { text-decoration: underline; }
.log-icon { flex-shrink: 0; width: 16px; text-align: center; }
.log-container { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); max-height: 70vh; overflow-y: auto; }
.audit-row { cursor: pointer; }
.audit-row:hover { background: rgba(56,189,248,0.06); }
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 100; display: none; justify-content: center; align-items: start; padding: 40px; overflow-y: auto; }
.modal-overlay.open { display: flex; }
.modal { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; max-width: 900px; width: 100%; max-height: 85vh; overflow-y: auto; }
.modal h3 { color: var(--accent); margin-bottom: 12px; }
.modal pre { max-height: 50vh; }
</style>
</head>
<body>
<div class="app">
  <header>
    <h1>TokenBurn Agent V2</h1>
    <div class="meta" id="meta">Loading...</div>
  </header>
  <div class="cards" id="stats"></div>
  <div class="tabs">
    <div class="tab active" data-tab="tasks">Tasks</div>
    <div class="tab" data-tab="detail" id="detail-tab" style="display:none">Task Detail</div>
    <div class="tab" data-tab="cycles">Cycles</div>
    <div class="tab" data-tab="activity">Activity Log</div>
    <div class="tab" data-tab="llm-audit">LLM Audit</div>
    <div class="tab" data-tab="control">Control</div>
    <div class="tab" data-tab="inject">Inject Task</div>
  </div>
  <div id="tasks" class="panel active"></div>
  <div id="detail" class="panel"></div>
  <div id="cycles" class="panel"></div>
  <div id="activity" class="panel"></div>
  <div id="llm-audit" class="panel"></div>
  <div id="control" class="panel"></div>
  <div id="inject" class="panel"></div>
</div>
<div class="toast" id="toast"></div>
<div class="modal-overlay" id="audit-modal" onclick="if(event.target===this)this.classList.remove('open')">
  <div class="modal" id="audit-modal-content"></div>
</div>
<script>
const API = '';
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
let activityAutoScroll = true;
let activityPhaseFilter = '';
let auditAutoRefresh = true;

document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
  $$('.tab').forEach(x => x.classList.remove('active'));
  $$('.panel').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  $('#' + t.dataset.tab).classList.add('active');
  if (t.dataset.tab === 'activity') refreshActivity();
  if (t.dataset.tab === 'llm-audit') refreshAudit();
}));

function toast(msg, ok=true) {
  const el = $('#toast');
  el.textContent = msg;
  el.style.background = ok ? '#34d399' : '#f87171';
  el.style.color = ok ? '#000' : '#fff';
  el.style.display = 'block';
  setTimeout(() => el.style.display = 'none', 3000);
}

function badge(status) {
  return `<span class="badge badge-${status}">${status}</span>`;
}

function phaseTag(phase) {
  return `<span class="phase-tag phase-${phase}">${phase}</span>`;
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function shortTime(iso) {
  if (!iso) return '';
  try { return iso.slice(11,19); } catch(e) { return iso; }
}

async function fetchJSON(url, opts) {
  const r = await fetch(API + url, opts);
  return r.json();
}

async function refreshAll() {
  try {
    const [taskData, cycleData, stats, dir] = await Promise.all([
      fetchJSON('/api/tasks'), fetchJSON('/api/cycles'),
      fetchJSON('/api/stats'), fetchJSON('/api/directive'),
    ]);
    renderStats(stats);
    renderTasks(taskData.tasks || []);
    renderCycles(cycleData.cycles || []);
    renderControl(dir);
    $('#meta').textContent = `updated: ${taskData.updated_at} | auto-refresh: 5s`;
  } catch(e) { $('#meta').textContent = 'Refresh failed: ' + e; }
}

function renderStats(s) {
  const counts = s.status_counts || {};
  let html = `<div class="card"><div class="label">Total</div><div class="value">${s.total_tasks||0}</div></div>`;
  html += `<div class="card"><div class="label">Cycles</div><div class="value">${s.total_cycles||0}</div></div>`;
  html += `<div class="card"><div class="label">Total Tokens</div><div class="value" style="font-size:18px">${(s.total_tokens||0).toLocaleString()}</div></div>`;
  for (const [k,v] of Object.entries(counts).sort((a,b)=>b[1]-a[1])) {
    html += `<div class="card"><div class="label">${k}</div><div class="value">${v}</div></div>`;
  }
  $('#stats').innerHTML = html;
}

function renderTasks(tasks) {
  let html = `<table><thead><tr>
    <th>Task</th><th>Source</th><th>Status</th><th>Pri</th>
    <th>Tokens</th><th>Time</th><th>Branch</th><th>PR</th><th>Updated</th></tr></thead><tbody>`;
  for (const t of tasks) {
    const pr = t.pr_url ? `<a class="pr-link" href="${esc(t.pr_url)}" target="_blank">View</a>` : '-';
    const tokens = t.token_cost ? t.token_cost.toLocaleString() : '-';
    const timeCost = t.time_cost_seconds ? t.time_cost_seconds.toFixed(1) + 's' : '-';
    html += `<tr style="cursor:pointer" onclick="showDetail('${esc(t.id)}')">
      <td><strong>${esc(t.title)}</strong><div class="mono" style="color:var(--muted)">${esc(t.id)}</div></td>
      <td>${esc(t.source)}</td>
      <td>${badge(t.status)}</td>
      <td>${t.priority}</td>
      <td class="mono">${tokens}</td>
      <td class="mono">${timeCost}</td>
      <td class="mono">${esc(t.branch_name || '-')}</td>
      <td>${pr}</td>
      <td class="mono">${(t.updated_at||'').slice(0,19)}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  $('#tasks').innerHTML = html;
}

function renderCycles(cycles) {
  let html = `<table><thead><tr>
    <th>ID</th><th>Status</th><th>Discovered</th><th>Executed</th>
    <th>Completed</th><th>Failed</th><th>Started</th><th>Finished</th>
  </tr></thead><tbody>`;
  for (const c of cycles) {
    html += `<tr>
      <td>${c.id}</td><td>${badge(c.status)}</td>
      <td>${c.discovered}</td><td>${c.executed}</td>
      <td>${c.completed}</td><td>${c.failed}</td>
      <td class="mono">${(c.started_at||'').slice(0,19)}</td>
      <td class="mono">${(c.completed_at||'').slice(0,19) || '-'}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  $('#cycles').innerHTML = html;
}

/* ────── Activity Log ────── */

async function refreshActivity() {
  try {
    const phase = activityPhaseFilter;
    let url = '/api/activity?limit=500';
    if (phase) url += '&phase=' + encodeURIComponent(phase);
    const data = await fetchJSON(url);
    renderActivity(data.events || []);
  } catch(e) { console.error('Activity refresh failed', e); }
}

function renderActivity(events) {
  const panel = $('#activity');
  const existing = panel.querySelector('.log-container');
  const wasAtBottom = existing
    ? (existing.scrollHeight - existing.scrollTop - existing.clientHeight < 40)
    : true;

  let toolbarHtml = `
    <div class="toolbar">
      <select id="activity-phase" onchange="activityPhaseFilter=this.value;refreshActivity()">
        <option value="">All Phases</option>
        <option value="cycle" ${activityPhaseFilter==='cycle'?'selected':''}>Cycle</option>
        <option value="discover" ${activityPhaseFilter==='discover'?'selected':''}>Discover</option>
        <option value="value" ${activityPhaseFilter==='value'?'selected':''}>Value</option>
        <option value="plan" ${activityPhaseFilter==='plan'?'selected':''}>Plan</option>
        <option value="execute" ${activityPhaseFilter==='execute'?'selected':''}>Execute</option>
        <option value="verify" ${activityPhaseFilter==='verify'?'selected':''}>Verify</option>
        <option value="git" ${activityPhaseFilter==='git'?'selected':''}>Git</option>
        <option value="system" ${activityPhaseFilter==='system'?'selected':''}>System</option>
        <option value="decision" ${activityPhaseFilter==='decision'?'selected':''}>Decision</option>
      </select>
      <label style="display:inline-flex;align-items:center;gap:4px;font-size:12px;color:var(--muted);margin:0">
        <input type="checkbox" id="activity-scroll" ${activityAutoScroll?'checked':''}
          onchange="activityAutoScroll=this.checked"> Auto-scroll
      </label>
      <button class="btn btn-sm btn-primary" onclick="refreshActivity()">Refresh</button>
      <span class="mono" style="color:var(--muted)">${events.length} events</span>
    </div>`;

  let rowsHtml = '';
  for (const e of events) {
    const icon = e.success === true ? '<span style="color:var(--ok)">&#10003;</span>'
      : e.success === false ? '<span style="color:var(--danger)">&#10007;</span>'
      : '';
    const taskLink = e.task_id
      ? `<span class="log-task" onclick="event.stopPropagation();showDetail('${esc(e.task_id)}')">${esc(e.task_id.slice(0,8))}</span>`
      : '';
    const reasoning = e.reasoning ? `<span style="color:var(--muted);font-style:italic"> — ${esc(e.reasoning.slice(0,150))}</span>` : '';

    rowsHtml += `<div class="log-row">
      <span class="log-time">${shortTime(e.timestamp)}</span>
      <span class="log-phase">${phaseTag(e.phase||'?')}</span>
      <span class="log-icon">${icon}</span>
      <span class="log-action">${esc(e.action||'')}</span>
      ${taskLink ? `<span style="flex-shrink:0">${taskLink}</span>` : ''}
      <span class="log-detail">${esc(e.detail||'')}${reasoning}</span>
    </div>`;
  }

  panel.innerHTML = toolbarHtml + `<div class="log-container">${rowsHtml}</div>`;

  if (activityAutoScroll && (wasAtBottom || !existing)) {
    const container = panel.querySelector('.log-container');
    container.scrollTop = container.scrollHeight;
  }
}

/* ────── LLM Audit ────── */

async function refreshAudit() {
  try {
    const data = await fetchJSON('/api/llm-audit?limit=100');
    renderAudit(data.entries || []);
  } catch(e) { console.error('Audit refresh failed', e); }
}

function renderAudit(entries) {
  let html = `
    <div class="toolbar">
      <button class="btn btn-sm btn-primary" onclick="refreshAudit()">Refresh</button>
      <span class="mono" style="color:var(--muted)">${entries.length} LLM calls</span>
    </div>
    <table><thead><tr>
      <th>#</th><th>Time</th><th>Model</th>
      <th>Prompt</th><th>Response</th>
      <th>Tokens</th><th>Latency</th>
    </tr></thead><tbody>`;

  for (const e of entries.slice().reverse()) {
    const promptPre = esc((e.prompt_preview||'').slice(0,120));
    const respPre = esc((e.response_preview||'').slice(0,120));
    const tokens = `${(e.prompt_tokens||0).toLocaleString()} / ${(e.completion_tokens||0).toLocaleString()}`;
    const latency = e.duration_ms ? (e.duration_ms/1000).toFixed(1)+'s' : '-';
    const errBadge = e.error ? `<span style="color:var(--danger)"> [ERR]</span>` : '';

    html += `<tr class="audit-row" onclick="showAuditDetail(${e.seq})">
      <td class="mono">${e.seq}</td>
      <td class="mono">${shortTime(e.ts)}</td>
      <td class="mono" style="font-size:11px">${esc(e.model||'-')}</td>
      <td style="max-width:250px"><div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;color:var(--muted)">${promptPre}</div></td>
      <td style="max-width:250px"><div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;color:var(--muted)">${respPre}${errBadge}</div></td>
      <td class="mono" style="font-size:11px">${tokens}</td>
      <td class="mono">${latency}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  $('#llm-audit').innerHTML = html;
}

async function showAuditDetail(seq) {
  try {
    const data = await fetchJSON('/api/llm-audit/' + seq);
    if (data.error) { toast(data.error, false); return; }
    const e = data.entry;
    const tokens = `prompt=${(e.prompt_tokens||0).toLocaleString()}, completion=${(e.completion_tokens||0).toLocaleString()}, total=${(e.total_tokens||0).toLocaleString()}`;
    const latency = e.duration_ms ? (e.duration_ms/1000).toFixed(2)+'s' : '-';

    $('#audit-modal-content').innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h3>LLM Call #${e.seq}</h3>
        <button class="btn btn-sm btn-danger" onclick="$('#audit-modal').classList.remove('open')">Close</button>
      </div>
      <div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(120px,1fr));margin-bottom:12px">
        <div class="card"><div class="label">Model</div><div class="value" style="font-size:14px">${esc(e.model||'-')}</div></div>
        <div class="card"><div class="label">Tokens</div><div class="value" style="font-size:14px">${esc(tokens)}</div></div>
        <div class="card"><div class="label">Latency</div><div class="value" style="font-size:18px">${latency}</div></div>
        <div class="card"><div class="label">Time</div><div class="value" style="font-size:14px">${esc(e.ts||'')}</div></div>
      </div>
      ${e.error ? `<div class="ctrl" style="border-color:var(--danger)"><h3 style="color:var(--danger)">Error</h3><pre style="color:var(--danger)">${esc(e.error)}</pre></div>` : ''}
      <div class="ctrl">
        <h3>Prompt (${(e.prompt_len||0).toLocaleString()} chars)</h3>
        <pre>${esc(e.prompt_full||e.prompt_preview||'(empty)')}</pre>
      </div>
      <div class="ctrl">
        <h3>Response (${(e.response_len||0).toLocaleString()} chars)</h3>
        <pre>${esc(e.response_full||e.response_preview||'(empty)')}</pre>
      </div>`;
    $('#audit-modal').classList.add('open');
  } catch(e) { toast('Load failed: '+e, false); }
}

/* ────── Control Panel ────── */

function renderControl(d) {
  $('#control').innerHTML = `
    <div class="ctrl">
      <h3>Agent Directive</h3>
      <div class="row">
        <div>
          <label>Status</label>
          <select id="d-paused">
            <option value="false" ${!d.paused?'selected':''}>Running</option>
            <option value="true" ${d.paused?'selected':''}>Paused</option>
          </select>
        </div>
        <div>
          <label>Poll Interval (seconds)</label>
          <input id="d-interval" type="number" value="${d.poll_interval_seconds}" min="10">
        </div>
        <div>
          <label>Max File Changes / Task</label>
          <input id="d-maxfiles" type="number" value="${d.max_file_changes_per_task}" min="1">
        </div>
      </div>
      <label>Focus Areas (comma-separated)</label>
      <input id="d-focus" value="${(d.focus_areas||[]).join(', ')}">
      <label>Forbidden Paths (comma-separated)</label>
      <input id="d-forbidden" value="${(d.forbidden_paths||[]).join(', ')}">
      <label>Custom Instructions</label>
      <textarea id="d-instructions">${d.custom_instructions||''}</textarea>
      <label>Task Sources (JSON)</label>
      <textarea id="d-sources" class="mono">${JSON.stringify(d.task_sources||{},null,2)}</textarea>
      <br><button class="btn btn-primary" onclick="saveDirective()">Save Directive</button>
    </div>`;
}

async function saveDirective() {
  try {
    const body = {
      paused: $('#d-paused').value === 'true',
      poll_interval_seconds: parseInt($('#d-interval').value),
      max_file_changes_per_task: parseInt($('#d-maxfiles').value),
      focus_areas: $('#d-focus').value.split(',').map(s=>s.trim()).filter(Boolean),
      forbidden_paths: $('#d-forbidden').value.split(',').map(s=>s.trim()).filter(Boolean),
      custom_instructions: $('#d-instructions').value,
      task_sources: JSON.parse($('#d-sources').value),
    };
    await fetchJSON('/api/directive', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    toast('Directive saved');
    refreshAll();
  } catch(e) { toast('Save failed: '+e, false); }
}

/* ────── Inject Task ────── */

$('#inject').innerHTML = `
  <div class="ctrl">
    <h3>Inject Manual Task</h3>
    <label>Title</label>
    <input id="inj-title" placeholder="Task title...">
    <label>Description</label>
    <textarea id="inj-desc" placeholder="Detailed description..."></textarea>
    <label>Priority (1=highest, 5=lowest)</label>
    <input id="inj-priority" type="number" value="2" min="1" max="5">
    <br><button class="btn btn-ok" onclick="injectTask()">Inject Task</button>
  </div>`;

async function injectTask() {
  const title = $('#inj-title').value.trim();
  if (!title) { toast('Title required', false); return; }
  try {
    await fetchJSON('/api/tasks/inject', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({title, description:$('#inj-desc').value, priority:parseInt($('#inj-priority').value)})
    });
    toast('Task injected');
    $('#inj-title').value = '';
    $('#inj-desc').value = '';
    refreshAll();
  } catch(e) { toast('Inject failed: '+e, false); }
}

/* ────── Task Detail ────── */

async function showDetail(taskId) {
  try {
    const data = await fetchJSON('/api/tasks/' + taskId);
    if (data.error) { toast(data.error, false); return; }
    renderDetail(data.task, data.events || []);
    $$('.tab').forEach(x => x.classList.remove('active'));
    $$('.panel').forEach(x => x.classList.remove('active'));
    const dt = $('#detail-tab');
    dt.style.display = '';
    dt.classList.add('active');
    dt.textContent = 'Task: ' + (data.task.title||'').slice(0,30);
    $('#detail').classList.add('active');
  } catch(e) { toast('Load failed: '+e, false); }
}

function renderDetail(t, events) {
  const pr = t.pr_url ? `<a class="pr-link" href="${esc(t.pr_url)}" target="_blank">${esc(t.pr_url)}</a>` : 'N/A';
  const tokens = t.token_cost ? t.token_cost.toLocaleString() : '0';
  const timeCost = t.time_cost_seconds ? t.time_cost_seconds.toFixed(1) + 's' : '0s';

  let planDisplay = '';
  try {
    const planObj = JSON.parse(t.plan || '{}');
    planDisplay = JSON.stringify(planObj, null, 2);
  } catch(e) { planDisplay = t.plan || '(empty)'; }

  let eventHtml = '<table><thead><tr><th>Time</th><th>Event</th><th>Detail</th></tr></thead><tbody>';
  for (const ev of events) {
    eventHtml += `<tr>
      <td class="mono">${(ev.created_at||'').slice(0,19)}</td>
      <td>${esc(ev.event_type)}</td>
      <td style="max-width:500px;word-break:break-all">${esc(ev.detail||'')}</td>
    </tr>`;
  }
  eventHtml += '</tbody></table>';

  $('#detail').innerHTML = `
    <div style="margin-bottom:12px">
      <button class="btn btn-primary" onclick="
        $$('.tab').forEach(x=>x.classList.remove('active'));
        $$('.panel').forEach(x=>x.classList.remove('active'));
        document.querySelector('[data-tab=tasks]').classList.add('active');
        $('#tasks').classList.add('active');
      ">&larr; Back to Tasks</button>
    </div>
    <div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(120px,1fr))">
      <div class="card"><div class="label">Status</div><div class="value" style="font-size:18px">${badge(t.status)}</div></div>
      <div class="card"><div class="label">Priority</div><div class="value">${t.priority}</div></div>
      <div class="card"><div class="label">Tokens</div><div class="value" style="font-size:18px">${tokens}</div></div>
      <div class="card"><div class="label">Time</div><div class="value" style="font-size:18px">${timeCost}</div></div>
      <div class="card"><div class="label">Cycle</div><div class="value">${t.cycle_id||'-'}</div></div>
      <div class="card"><div class="label">Source</div><div class="value" style="font-size:14px">${esc(t.source)}</div></div>
    </div>
    <div class="ctrl">
      <h3>${esc(t.title)}</h3>
      <div class="mono" style="color:var(--muted);margin-bottom:8px">ID: ${esc(t.id)}</div>
      <label>Description</label>
      <pre>${esc(t.description || '(empty)')}</pre>
      <label>Branch</label>
      <div class="mono">${esc(t.branch_name || 'N/A')}</div>
      <label>Pull Request</label>
      <div>${pr}</div>
    </div>
    <div class="ctrl">
      <h3>Execution Plan</h3>
      <pre>${esc(planDisplay)}</pre>
    </div>
    <div class="ctrl">
      <h3>Execution Log</h3>
      <pre>${esc(t.execution_log || '(empty)')}</pre>
    </div>
    <div class="ctrl">
      <h3>Verification Result</h3>
      <pre>${esc(t.verification_result || '(empty)')}</pre>
    </div>
    ${t.error_message ? `<div class="ctrl">
      <h3 style="color:var(--danger)">Error</h3>
      <pre style="color:var(--danger)">${esc(t.error_message)}</pre>
    </div>` : ''}
    <div class="ctrl">
      <h3>What Was Learned</h3>
      <pre>${esc(t.whats_learned || '(nothing extracted)')}</pre>
    </div>
    <div class="ctrl">
      <h3>Event Timeline (${events.length} events)</h3>
      ${eventHtml}
    </div>`;
}

/* ────── Init ────── */

refreshAll();
setInterval(refreshAll, 5000);
setInterval(() => {
  if ($('#activity').classList.contains('active')) refreshActivity();
}, 3000);
setInterval(() => {
  if ($('#llm-audit').classList.contains('active') && auditAutoRefresh) refreshAudit();
}, 5000);
</script>
</body>
</html>"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional

from llm247.autonomous import AutonomousStateStore
from llm247.scheduler import is_task_due
from llm247.storage import TaskStateStore
from llm247.tasks import build_default_tasks


# Build a unified task snapshot for autonomous and legacy runtimes.
def build_task_snapshot(
    workspace_path: Path,
    autonomous_state_path: Path,
    legacy_state_path: Path,
    now: Optional[datetime] = None,
) -> Dict[str, object]:
    """Return API payload with all known task statuses and progress."""
    snapshot_time = now or datetime.now(timezone.utc)

    autonomous_tasks = _build_autonomous_tasks(autonomous_state_path)
    legacy_tasks = _build_legacy_tasks(legacy_state_path, snapshot_time)
    tasks = autonomous_tasks + legacy_tasks

    status_counts: Dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "workspace": str(workspace_path),
        "updated_at": snapshot_time.isoformat(),
        "summary": {
            "task_count": len(tasks),
            "status_counts": status_counts,
        },
        "tasks": tasks,
    }


# Render the control-plane page for browser usage.
def render_dashboard_html() -> str:
    """Return dashboard HTML with styles and polling script."""
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>llm247 Control Plane</title>
  <style>
    :root {
      --bg: radial-gradient(1200px 600px at 10% -20%, #133a5e 0%, #08111c 40%, #060b12 100%);
      --panel: rgba(11, 18, 28, 0.78);
      --panel-border: rgba(137, 190, 255, 0.26);
      --text: #eaf2ff;
      --muted: #99acc2;
      --accent: #51d0ff;
      --ok: #35d07f;
      --warn: #f8c053;
      --danger: #ff6c7e;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
      min-height: 100vh;
      padding: 24px;
    }
    .shell {
      max-width: 1180px;
      margin: 0 auto;
      display: grid;
      gap: 16px;
    }
    .hero {
      background: linear-gradient(135deg, rgba(22, 35, 57, 0.95), rgba(12, 19, 30, 0.85));
      border: 1px solid var(--panel-border);
      border-radius: 16px;
      padding: 20px;
      backdrop-filter: blur(10px);
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
    }
    .hero h1 { margin: 0; font-size: 28px; letter-spacing: 0.2px; }
    .hero .meta { margin-top: 8px; color: var(--muted); font-family: "Space Mono", monospace; font-size: 13px; }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 14px;
      padding: 14px;
      min-height: 92px;
    }
    .card .label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }
    .card .value { margin-top: 8px; font-size: 28px; font-weight: 700; }
    .table-wrap {
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 16px;
      overflow: hidden;
    }
    table { width: 100%; border-collapse: collapse; }
    thead { background: rgba(81, 208, 255, 0.08); }
    th, td {
      text-align: left;
      padding: 12px 14px;
      border-bottom: 1px solid rgba(137, 190, 255, 0.12);
      font-size: 14px;
      vertical-align: top;
    }
    th { color: #dff2ff; font-size: 12px; letter-spacing: 0.8px; text-transform: uppercase; }
    .status {
      display: inline-block;
      padding: 3px 9px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.3px;
    }
    .status-running { background: rgba(81, 208, 255, 0.14); color: var(--accent); }
    .status-completed { background: rgba(53, 208, 127, 0.14); color: var(--ok); }
    .status-due { background: rgba(248, 192, 83, 0.14); color: var(--warn); }
    .status-waiting, .status-pending, .status-idle { background: rgba(153, 172, 194, 0.2); color: #dce8f8; }
    .status-unknown, .status-interrupted, .status-budget_exhausted { background: rgba(255, 108, 126, 0.14); color: var(--danger); }
    .tiny { color: var(--muted); font-family: "Space Mono", monospace; font-size: 12px; }
    @media (max-width: 760px) {
      body { padding: 12px; }
      .hero h1 { font-size: 22px; }
      th:nth-child(7), td:nth-child(7), th:nth-child(8), td:nth-child(8) { display: none; }
    }
  </style>
</head>
<body>
  <div class=\"shell\">
    <section class=\"hero\">
      <h1>llm247 Control Plane</h1>
      <div class=\"meta\" id=\"meta\">Loading...</div>
    </section>

    <section class=\"cards\" id=\"summary-cards\"></section>

    <section class=\"table-wrap\">
      <table>
        <thead>
          <tr>
            <th>Task</th>
            <th>Group</th>
            <th>Status</th>
            <th>Iteration</th>
            <th>Elapsed(s)</th>
            <th>Progress</th>
            <th>Updated</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody id=\"task-table-body\"></tbody>
      </table>
    </section>
  </div>

  <script>
    const statusClass = (status) => `status status-${status || 'unknown'}`;

    function renderSummary(summary) {
      const cards = document.getElementById('summary-cards');
      const statusCounts = summary.status_counts || {};
      const entries = Object.entries(statusCounts).sort((a, b) => b[1] - a[1]);
      const statusHtml = entries.map(([name, count]) => `
        <article class=\"card\">
          <div class=\"label\">${name}</div>
          <div class=\"value\">${count}</div>
        </article>
      `).join('');

      cards.innerHTML = `
        <article class=\"card\">
          <div class=\"label\">Total Tasks</div>
          <div class=\"value\">${summary.task_count || 0}</div>
        </article>
      ` + statusHtml;
    }

    function renderTasks(tasks) {
      const body = document.getElementById('task-table-body');
      body.innerHTML = tasks.map((task) => `
        <tr>
          <td><strong>${task.title || task.id}</strong><div class=\"tiny\">${task.id}</div></td>
          <td>${task.group || '-'}</td>
          <td><span class=\"${statusClass(task.status)}\">${task.status || 'unknown'}</span></td>
          <td>${task.iteration || 0}</td>
          <td>${Number(task.elapsed_seconds || 0).toFixed(2)}</td>
          <td>${task.progress || '-'}</td>
          <td class=\"tiny\">${task.updated_at || '-'}</td>
          <td class=\"tiny\">${task.details || '-'}</td>
        </tr>
      `).join('');
    }

    async function refresh() {
      const response = await fetch('/api/tasks');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();

      document.getElementById('meta').textContent =
        `workspace=${payload.workspace} | updated=${payload.updated_at} | auto-refresh=5s`;

      renderSummary(payload.summary || {});
      renderTasks(payload.tasks || []);
    }

    async function tick() {
      try {
        await refresh();
      } catch (error) {
        document.getElementById('meta').textContent = `Dashboard refresh failed: ${error}`;
      }
    }

    tick();
    setInterval(tick, 5000);
  </script>
</body>
</html>
"""


# Run control-plane server for task visibility in browser.
def serve_control_plane(
    workspace_path: Path,
    autonomous_state_path: Path,
    legacy_state_path: Path,
    host: str,
    port: int,
) -> None:
    """Start HTTP server that exposes task snapshot API and dashboard page."""

    class DashboardHandler(BaseHTTPRequestHandler):
        """HTTP request handler for dashboard assets and task API."""

        def do_GET(self) -> None:  # noqa: N802
            """Serve dashboard page and JSON task endpoint."""
            if self.path in {"/", "/index.html"}:
                html = render_dashboard_html().encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return

            if self.path == "/api/tasks":
                payload = build_task_snapshot(
                    workspace_path=workspace_path,
                    autonomous_state_path=autonomous_state_path,
                    legacy_state_path=legacy_state_path,
                )
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

        def log_message(self, format: str, *args: object) -> None:
            """Bridge HTTP server logs into project logger."""
            logging.getLogger("llm247.dashboard").info(format, *args)

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    logger = logging.getLogger("llm247.dashboard")
    logger.info("control plane listening at http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("control plane interrupted, shutting down")
    finally:
        server.shutdown()
        server.server_close()


# Build rows describing autonomous runtime current and pending actions.
def _build_autonomous_tasks(autonomous_state_path: Path) -> List[Dict[str, object]]:
    """Return autonomous task rows from persisted runtime state."""
    state = AutonomousStateStore(autonomous_state_path).load()
    rows: List[Dict[str, object]] = []

    title = state.current_task or state.active_goal or "Autonomous Goal"
    progress = "{completed}/{total}".format(
        completed=state.progress_completed_actions,
        total=state.progress_total_actions,
    )
    rows.append(
        {
            "id": "autonomous.current",
            "title": title,
            "group": "autonomous",
            "status": state.status or "idle",
            "iteration": state.current_task_iteration,
            "elapsed_seconds": state.current_task_elapsed_seconds,
            "progress": progress,
            "updated_at": state.updated_at or "-",
            "details": state.last_cycle_observations[:200] if state.last_cycle_observations else "-",
        }
    )

    for index, action in enumerate(state.pending_actions, start=1):
        action_title = action.action_type
        if action.command:
            action_title += " " + " ".join(action.command)
        elif action.query:
            action_title += " " + action.query
        elif action.path:
            action_title += " " + action.path

        rows.append(
            {
                "id": f"autonomous.pending.{index}",
                "title": action_title,
                "group": "autonomous",
                "status": "pending",
                "iteration": state.current_task_iteration,
                "elapsed_seconds": state.current_task_elapsed_seconds,
                "progress": f"{index}/{len(state.pending_actions)}",
                "updated_at": state.updated_at or "-",
                "details": state.pending_rationale or "-",
            }
        )

    return rows


# Build rows describing legacy fixed tasks and due status.
def _build_legacy_tasks(legacy_state_path: Path, now: datetime) -> List[Dict[str, object]]:
    """Return legacy task rows by comparing last run time and intervals."""
    store = TaskStateStore(legacy_state_path)
    rows: List[Dict[str, object]] = []

    for task in build_default_tasks():
        last_run = store.get_last_run(task.name)
        if last_run is None:
            status = "never_run"
            details = "No successful runs recorded"
            updated_at = "-"
        else:
            due = is_task_due(now=now, last_run_at=last_run, interval_seconds=task.interval_seconds)
            status = "due" if due else "waiting"
            updated_at = last_run.isoformat()
            details = f"interval={task.interval_seconds}s"

        rows.append(
            {
                "id": f"legacy.{task.name}",
                "title": task.name,
                "group": "legacy",
                "status": status,
                "iteration": store.get_run_count(task.name),
                "elapsed_seconds": store.get_total_duration_seconds(task.name),
                "progress": "-",
                "updated_at": updated_at,
                "details": details,
            }
        )

    return rows

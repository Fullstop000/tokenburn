"""Centralized observability layer for the autonomous agent.

Provides a single ``emit()`` entry point that routes structured events to
multiple handlers: human-readable activity log, machine-parseable JSONL,
SQLite event store, and optional console output.

Usage from agent code::

    obs = Observer(handlers=[
        HumanLogHandler(log_path),
        JsonLogHandler(jsonl_path),
        StoreHandler(task_store),
    ])
    obs.emit(AgentEvent(phase="cycle", action="started", detail="Cycle #42"))

Designed so humans can ``tail -f .llm247_v2/activity.log`` and see a clear,
timestamped narrative of everything the agent does and *why*.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("llm247_v2.observability.observer")

# ──────────────────────────────────────────────
# Event model
# ──────────────────────────────────────────────

PHASE_LABELS = {
    "cycle":    "CYCLE   ",
    "discover": "DISCOVER",
    "value":    "VALUE   ",
    "plan":     "PLAN    ",
    "execute":  "EXECUTE ",
    "verify":   "VERIFY  ",
    "git":      "GIT     ",
    "system":   "SYSTEM  ",
    "decision": "DECISION",
}


@dataclass(frozen=True)
class AgentEvent:
    """One atomic observable action or decision by the agent."""

    phase: str
    action: str
    detail: str = ""
    task_id: str = ""
    cycle_id: int = 0
    success: Optional[bool] = None
    reasoning: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ──────────────────────────────────────────────
# Handler interface
# ──────────────────────────────────────────────

class EventHandler(ABC):
    @abstractmethod
    def handle(self, event: AgentEvent) -> None: ...

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


# ──────────────────────────────────────────────
# Human-readable activity log  (tail -f friendly)
# ──────────────────────────────────────────────

_RESULT_ICON = {True: "✓", False: "✗", None: ""}


class HumanLogHandler(EventHandler):
    """Writes a concise, human-readable activity log.

    Output format::

        14:30:22 │ DISCOVER │ Strategy: change_hotspot │ queue=3
        14:30:25 │ VALUE    │ [abc123] score=0.82 ✓ Fix parser edge case
        14:30:27 │ EXECUTE  │ [1/3] edit_file src/parser.py ✓
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.Lock()
        self._file = open(path, "a", encoding="utf-8", buffering=1)

    def handle(self, event: AgentEvent) -> None:
        line = self._format(event)
        with self._lock:
            self._file.write(line + "\n")

    def flush(self) -> None:
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def _format(self, e: AgentEvent) -> str:
        ts = _short_time(e.timestamp)
        phase = PHASE_LABELS.get(e.phase, e.phase.upper().ljust(8))
        icon = _RESULT_ICON.get(e.success, "")

        parts = [ts, phase]

        if e.task_id:
            parts.append(f"[{e.task_id[:8]}]")

        parts.append(e.action)

        if e.detail:
            parts.append(e.detail)

        if icon:
            parts.append(icon)

        if e.reasoning:
            parts.append(f"  reason: {e.reasoning[:120]}")

        if e.phase == "cycle" and e.action == "separator":
            return f"\n{'━' * 60}"

        return " │ ".join(parts)


# ──────────────────────────────────────────────
# Machine-parseable JSONL log
# ──────────────────────────────────────────────

class JsonLogHandler(EventHandler):
    """Appends one JSON object per line — for programmatic analysis."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._file = open(path, "a", encoding="utf-8", buffering=1)

    def handle(self, event: AgentEvent) -> None:
        data = asdict(event)
        data = {k: v for k, v in data.items() if v or v == 0}
        with self._lock:
            self._file.write(json.dumps(data, ensure_ascii=False) + "\n")

    def flush(self) -> None:
        self._file.flush()

    def close(self) -> None:
        self._file.close()


# ──────────────────────────────────────────────
# SQLite store handler  (replaces scattered add_event calls)
# ──────────────────────────────────────────────

class StoreHandler(EventHandler):
    """Persists events into the TaskStore's task_events table."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def handle(self, event: AgentEvent) -> None:
        if not event.task_id:
            return
        detail_parts = [event.detail]
        if event.reasoning:
            detail_parts.append(f"[reason: {event.reasoning[:200]}]")
        if event.success is not None:
            detail_parts.append(f"[{'ok' if event.success else 'fail'}]")
        detail = " ".join(p for p in detail_parts if p)
        self._store.add_event(event.task_id, f"{event.phase}.{event.action}", detail)


# ──────────────────────────────────────────────
# Console handler (colored terminal output)
# ──────────────────────────────────────────────

_ANSI = {
    "reset": "\033[0m",
    "bold":  "\033[1m",
    "dim":   "\033[2m",
    "green": "\033[32m",
    "red":   "\033[31m",
    "cyan":  "\033[36m",
    "yellow":"\033[33m",
    "blue":  "\033[34m",
}

_PHASE_COLOR = {
    "cycle":    "bold",
    "discover": "cyan",
    "value":    "blue",
    "plan":     "yellow",
    "execute":  "green",
    "verify":   "green",
    "git":      "cyan",
    "system":   "red",
    "decision": "yellow",
}


class ConsoleHandler(EventHandler):
    """Prints colored events to stderr for real-time terminal monitoring."""

    def __init__(self, use_color: bool = True) -> None:
        self._color = use_color and hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

    def handle(self, event: AgentEvent) -> None:
        line = self._format(event)
        sys.stderr.write(line + "\n")
        sys.stderr.flush()

    def _format(self, e: AgentEvent) -> str:
        ts = _short_time(e.timestamp)
        phase = PHASE_LABELS.get(e.phase, e.phase.upper().ljust(8))
        icon = _RESULT_ICON.get(e.success, "")

        parts = []
        if e.task_id:
            parts.append(f"[{e.task_id[:8]}]")
        parts.append(e.action)
        if e.detail:
            parts.append(e.detail)
        if icon:
            parts.append(icon)

        body = " ".join(parts)

        if not self._color:
            return f"{ts} │ {phase} │ {body}"

        color_name = _PHASE_COLOR.get(e.phase, "reset")
        c = _ANSI.get(color_name, "")
        r = _ANSI["reset"]
        dim = _ANSI["dim"]

        if e.phase == "cycle" and e.action == "separator":
            return f"{dim}{'━' * 60}{r}"

        return f"{dim}{ts}{r} │ {c}{phase}{r} │ {body}"


# ──────────────────────────────────────────────
# Observer (facade)
# ──────────────────────────────────────────────

class Observer:
    """Central dispatch: emit once, deliver to all handlers."""

    def __init__(self, handlers: Optional[List[EventHandler]] = None) -> None:
        self._handlers: List[EventHandler] = list(handlers or [])

    def add_handler(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def emit(self, event: AgentEvent) -> None:
        for h in self._handlers:
            try:
                h.handle(event)
            except Exception:
                logger.debug("Handler %s failed for event %s", type(h).__name__, event.action, exc_info=True)

    # ── convenience emitters ──────────────────

    def cycle_start(self, cycle_id: int) -> None:
        self.emit(AgentEvent(phase="cycle", action="separator"))
        self.emit(AgentEvent(phase="cycle", action="started", detail=f"Cycle #{cycle_id}", cycle_id=cycle_id))

    def cycle_end(self, cycle_id: int, discovered: int, executed: int, completed: int, failed: int) -> None:
        self.emit(AgentEvent(
            phase="cycle", action="completed", cycle_id=cycle_id,
            detail=f"+{discovered} discovered │ {executed} executed │ {completed} ok │ {failed} fail",
            success=failed == 0,
        ))

    def cycle_paused(self) -> None:
        self.emit(AgentEvent(phase="cycle", action="paused", detail="directive.paused=true"))

    def cycle_error(self, cycle_id: int, error: str) -> None:
        self.emit(AgentEvent(phase="cycle", action="error", cycle_id=cycle_id, detail=error[:300], success=False))

    def discover_strategy(self, strategy_name: str, queued: int, reasoning: str = "") -> None:
        self.emit(AgentEvent(
            phase="discover", action="strategy_selected",
            detail=f"{strategy_name} │ queue={queued}",
            reasoning=reasoning,
        ))

    def discover_candidates(self, raw_count: int, filtered_count: int, final_count: int) -> None:
        self.emit(AgentEvent(
            phase="discover", action="candidates",
            detail=f"{raw_count} raw → {filtered_count} filtered → {final_count} selected",
        ))

    def discover_skipped(self, queued: int) -> None:
        self.emit(AgentEvent(
            phase="discover", action="skipped",
            detail=f"queue already has {queued} tasks",
            reasoning="Token conservation: skip discovery when queue is not empty",
        ))

    def discover_raw_candidates(self, candidates: list[dict]) -> None:
        """Log all raw candidates found during discovery before filtering."""
        for c in candidates:
            self.emit(AgentEvent(
                phase="discover", action="candidate_found",
                detail=f"[{c.get('source', '?')}] {c.get('title', '?')[:70]}",
                task_id=c.get("id", ""),
            ))

    def discover_value_scored(self, task_id: str, title: str, score: float, recommendation: str, dimensions: str) -> None:
        """Log the value assessment result for a single candidate."""
        ok = recommendation == "execute"
        self.emit(AgentEvent(
            phase="value", action="scored",
            task_id=task_id,
            detail=f"score={score:.3f} rec={recommendation} │ {title[:50]}",
            reasoning=dimensions,
            success=ok,
        ))

    def discover_filtered_out(self, task_id: str, title: str, score: float, reason: str) -> None:
        """Log a candidate that was filtered out with the reason."""
        self.emit(AgentEvent(
            phase="value", action="filtered_out",
            task_id=task_id,
            detail=f"score={score:.3f} │ {title[:50]}",
            reasoning=reason,
            success=False,
        ))

    def discover_summary(self, raw: int, after_heuristic: int, after_llm: int, final: int) -> None:
        """Log the full discovery funnel in one event."""
        self.emit(AgentEvent(
            phase="discover", action="funnel",
            detail=f"raw={raw} → heuristic={after_heuristic} → llm={after_llm} → final={final}",
        ))

    def experience_injected(self, task_id: str, count: int, summaries: str) -> None:
        """Log which past experiences were injected into planning."""
        self.emit(AgentEvent(
            phase="plan", action="experience_injected",
            task_id=task_id,
            detail=f"{count} experiences",
            reasoning=summaries[:200],
        ))

    def value_assessed(self, task_id: str, title: str, score: float, recommendation: str) -> None:
        ok = recommendation == "execute"
        self.emit(AgentEvent(
            phase="value", action="assessed", task_id=task_id,
            detail=f"score={score:.2f} {recommendation} │ {title[:60]}",
            success=ok,
        ))

    def task_queued(self, task_id: str, title: str, source: str) -> None:
        self.emit(AgentEvent(
            phase="discover", action="queued", task_id=task_id,
            detail=f"{title[:50]} (source={source})",
        ))

    def plan_started(self, task_id: str, title: str) -> None:
        self.emit(AgentEvent(phase="plan", action="started", task_id=task_id, detail=title[:60]))

    def plan_created(self, task_id: str, step_count: int, commit_msg: str) -> None:
        self.emit(AgentEvent(
            phase="plan", action="created", task_id=task_id,
            detail=f"{step_count} steps │ {commit_msg[:50]}",
            success=True,
        ))

    def replan_triggered(self, task_id: str, round_number: int, trigger: str) -> None:
        self.emit(AgentEvent(
            phase="plan", action="replan_triggered", task_id=task_id,
            detail=f"round={round_number} trigger={trigger}",
        ))

    def replan_created(self, task_id: str, round_number: int, step_count: int) -> None:
        self.emit(AgentEvent(
            phase="plan", action="replan_created", task_id=task_id,
            detail=f"round={round_number} steps={step_count}",
            success=True,
        ))

    def replan_exhausted(self, task_id: str, total_rounds: int) -> None:
        self.emit(AgentEvent(
            phase="plan", action="replan_exhausted", task_id=task_id,
            detail=f"exhausted after {total_rounds} rounds",
            success=False,
        ))

    def plan_blocked(self, task_id: str, reason: str) -> None:
        self.emit(AgentEvent(
            phase="plan", action="constitution_blocked", task_id=task_id,
            detail=reason, success=False,
        ))

    def execute_step(self, task_id: str, step_index: int, total: int, action: str, target: str, success: bool, output: str = "") -> None:
        self.emit(AgentEvent(
            phase="execute",
            action=f"step [{step_index + 1}/{total}]",
            task_id=task_id,
            detail=f"{action} {target}" + (f" │ {output[:80]}" if output and not success else ""),
            success=success,
        ))

    def execute_finished(self, task_id: str, all_ok: bool) -> None:
        self.emit(AgentEvent(
            phase="execute", action="finished", task_id=task_id,
            detail="all steps passed" if all_ok else "one or more steps failed",
            success=all_ok,
        ))

    def verify_result(self, task_id: str, passed: bool, summary: str) -> None:
        self.emit(AgentEvent(
            phase="verify", action="completed", task_id=task_id,
            detail=summary[:100], success=passed,
        ))

    def git_worktree(self, task_id: str, branch: str, success: bool) -> None:
        self.emit(AgentEvent(
            phase="git", action="worktree", task_id=task_id,
            detail=f"branch={branch}", success=success,
        ))

    def git_committed(self, task_id: str, message: str) -> None:
        self.emit(AgentEvent(phase="git", action="committed", task_id=task_id, detail=message[:60], success=True))

    def git_pushed(self, task_id: str) -> None:
        self.emit(AgentEvent(phase="git", action="pushed", task_id=task_id, success=True))

    def git_pr(self, task_id: str, url: str, success: bool) -> None:
        self.emit(AgentEvent(phase="git", action="pr_created" if success else "pr_failed", task_id=task_id, detail=url[:120], success=success))

    def task_completed(self, task_id: str, title: str) -> None:
        self.emit(AgentEvent(phase="execute", action="task_completed", task_id=task_id, detail=title[:60], success=True))

    def task_failed(self, task_id: str, reason: str) -> None:
        self.emit(AgentEvent(phase="execute", action="task_failed", task_id=task_id, detail=reason[:120], success=False))

    def task_needs_human(self, task_id: str, reason: str) -> None:
        self.emit(AgentEvent(phase="execute", action="task_needs_human", task_id=task_id, detail=reason[:120], success=False))

    def decision(self, description: str, reasoning: str, task_id: str = "") -> None:
        self.emit(AgentEvent(phase="decision", action="made", task_id=task_id, detail=description, reasoning=reasoning))

    def system_event(self, action: str, detail: str = "", success: Optional[bool] = None) -> None:
        self.emit(AgentEvent(phase="system", action=action, detail=detail, success=success))

    def flush(self) -> None:
        for h in self._handlers:
            try:
                h.flush()
            except Exception:
                pass

    def close(self) -> None:
        for h in self._handlers:
            try:
                h.close()
            except Exception:
                pass


# ──────────────────────────────────────────────
# Null observer (for tests / no-op usage)
# ──────────────────────────────────────────────

class NullObserver(Observer):
    """Observer that discards all events — useful for tests."""

    def __init__(self) -> None:
        super().__init__(handlers=[])

    def emit(self, event: AgentEvent) -> None:
        pass


# ──────────────────────────────────────────────
# In-memory collector (for tests)
# ──────────────────────────────────────────────

class MemoryHandler(EventHandler):
    """Collects events in a list — for assertions in tests."""

    def __init__(self) -> None:
        self.events: List[AgentEvent] = []

    def handle(self, event: AgentEvent) -> None:
        self.events.append(event)

    def find(self, phase: str = "", action: str = "") -> List[AgentEvent]:
        return [
            e for e in self.events
            if (not phase or e.phase == phase)
            and (not action or e.action == action)
        ]


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _short_time(iso_timestamp: str) -> str:
    """Extract HH:MM:SS from ISO timestamp for compact display."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        return dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return time.strftime("%H:%M:%S")


def create_default_observer(
    state_dir: Path,
    store: Any = None,
    console: bool = True,
) -> Observer:
    """Factory: build the standard Observer with all handlers wired."""
    handlers: List[EventHandler] = [
        HumanLogHandler(state_dir / "activity.log"),
        JsonLogHandler(state_dir / "activity.jsonl"),
    ]
    if store is not None:
        handlers.append(StoreHandler(store))
    if console:
        handlers.append(ConsoleHandler())
    return Observer(handlers=handlers)

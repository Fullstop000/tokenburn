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
    obs.emit(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_started", detail="Cycle #42"))

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
from uuid import uuid4

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

MODULE_TO_PHASE = {
    "Cycle": "cycle",
    "Discovery": "discover",
    "Execution": "execute",
    "Memory": "plan",
    "Inbox": "system",
    "LLM": "decision",
    "ControlPlane": "system",
}

PHASE_TO_MODULE = {
    "cycle": "Cycle",
    "discover": "Discovery",
    "value": "Discovery",
    "plan": "Execution",
    "execute": "Execution",
    "verify": "Execution",
    "git": "Execution",
    "system": "ControlPlane",
    "decision": "LLM",
}

ACTION_TO_FAMILY = {
    "strategy_selected": "strategy",
    "candidate_found": "candidate",
    "queued": "queue",
    "candidates": "funnel",
    "funnel": "funnel",
    "scored": "valuation",
    "filtered_out": "valuation",
    "assessed": "valuation",
    "started": "planning",
    "created": "planning",
    "replan_triggered": "planning",
    "replan_created": "planning",
    "replan_exhausted": "planning",
    "constitution_blocked": "planning",
    "experience_injected": "planning",
    "finished": "state",
    "completed": "verification",
    "task_completed": "state",
    "task_failed": "state",
    "task_needs_human": "state",
    "worktree": "tool_call",
    "committed": "tool_call",
    "pushed": "tool_call",
    "pr_created": "tool_call",
    "pr_failed": "tool_call",
    "made": "audit_link",
}


@dataclass(frozen=True)
class AgentEvent:
    """One atomic observable action or decision by the agent."""

    event_id: str = field(default_factory=lambda: uuid4().hex)
    phase: str = ""
    action: str = ""
    module: str = ""
    family: str = ""
    event_name: str = ""
    detail: str = ""
    task_id: str = ""
    cycle_id: int = 0
    thread_id: str = ""
    llm_seq: int = 0
    success: Optional[bool] = None
    reasoning: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        phase = self.phase or _phase_from_module(self.module)
        action = self.action or self.event_name
        module = self.module or _module_from_phase(phase)
        family = self.family or _family_from_action(action)
        event_name = self.event_name or action

        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "module", module)
        object.__setattr__(self, "family", family)
        object.__setattr__(self, "event_name", event_name)


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
        phase = PHASE_LABELS.get(e.phase, e.module.upper().ljust(8))
        icon = _RESULT_ICON.get(e.success, "")

        parts = [ts, phase]

        if e.task_id:
            parts.append(f"[{e.task_id[:8]}]")

        parts.append(e.event_name)

        if e.detail:
            parts.append(e.detail)

        if icon:
            parts.append(icon)

        if e.reasoning:
            parts.append(f"  reason: {e.reasoning[:120]}")

        if e.module == "Cycle" and e.event_name == "cycle_separator":
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
        self._store.add_event(event.task_id, f"{event.module}.{event.family}.{event.event_name}", detail)


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
        phase = PHASE_LABELS.get(e.phase, e.module.upper().ljust(8))
        icon = _RESULT_ICON.get(e.success, "")

        parts = []
        if e.task_id:
            parts.append(f"[{e.task_id[:8]}]")
        parts.append(e.event_name)
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

        if e.module == "Cycle" and e.event_name == "cycle_separator":
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
                logger.debug("Handler %s failed for event %s", type(h).__name__, event.event_name, exc_info=True)

    # ── convenience emitters ──────────────────

    def cycle_start(self, cycle_id: int) -> None:
        self.emit(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_separator"))
        self.emit(AgentEvent(
            module="Cycle", family="lifecycle", event_name="cycle_started",
            detail=f"Cycle #{cycle_id}", cycle_id=cycle_id,
        ))

    def cycle_end(self, cycle_id: int, discovered: int, executed: int, completed: int, failed: int) -> None:
        self.emit(AgentEvent(
            module="Cycle", family="lifecycle", event_name="cycle_completed", cycle_id=cycle_id,
            detail=f"+{discovered} discovered │ {executed} executed │ {completed} ok │ {failed} fail",
            success=failed == 0,
            data={
                "discovered": discovered,
                "executed": executed,
                "completed": completed,
                "failed": failed,
            },
        ))

    def cycle_paused(self) -> None:
        self.emit(AgentEvent(module="Cycle", family="lifecycle", event_name="cycle_paused", detail="directive.paused=true"))

    def cycle_error(self, cycle_id: int, error: str) -> None:
        self.emit(AgentEvent(
            module="Cycle", family="lifecycle", event_name="cycle_error",
            cycle_id=cycle_id, detail=error[:300], success=False,
        ))

    def discover_strategy(self, strategy_name: str, queued: int, reasoning: str = "") -> None:
        self.emit(AgentEvent(
            module="Discovery", family="strategy", event_name="strategy_selected",
            detail=f"{strategy_name} │ queue={queued}",
            reasoning=reasoning,
            data={
                "strategy_name": strategy_name,
                "queue_depth": queued,
            },
        ))

    def discover_candidates(self, raw_count: int, filtered_count: int, final_count: int) -> None:
        self.emit(AgentEvent(
            module="Discovery", family="funnel", event_name="candidates_summarized",
            detail=f"{raw_count} raw → {filtered_count} filtered → {final_count} selected",
            data={
                "raw_candidates": raw_count,
                "filtered_candidates": filtered_count,
                "queued": final_count,
            },
        ))

    def discover_skipped(self, queued: int) -> None:
        self.emit(AgentEvent(
            module="Discovery", family="strategy", event_name="strategy_skipped",
            detail=f"queue already has {queued} tasks",
            reasoning="Token conservation: skip discovery when queue is not empty",
            data={
                "queue_depth": queued,
                "skipped_reason": "queue_not_empty",
            },
        ))

    def discover_raw_candidates(self, candidates: list[dict]) -> None:
        """Log all raw candidates found during discovery before filtering."""
        for c in candidates:
            self.emit(AgentEvent(
                module="Discovery", family="candidate", event_name="candidate_found",
                detail=f"[{c.get('source', '?')}] {c.get('title', '?')[:70]}",
                task_id=c.get("id", ""),
                data={
                    "candidate_id": c.get("id", ""),
                    "source": c.get("source", ""),
                    "title": c.get("title", ""),
                    "file_path": c.get("file_path", ""),
                    "line": c.get("line"),
                },
            ))

    def discover_value_scored(self, task_id: str, title: str, score: float, recommendation: str, dimensions: str) -> None:
        """Log the value assessment result for a single candidate."""
        ok = recommendation == "execute"
        self.emit(AgentEvent(
            module="Discovery", family="valuation", event_name="candidate_scored",
            task_id=task_id,
            detail=f"score={score:.3f} rec={recommendation} │ {title[:50]}",
            reasoning=dimensions,
            success=ok,
            data={
                "candidate_id": task_id,
                "score": score,
                "decision": recommendation,
                "title": title,
            },
        ))

    def discover_filtered_out(self, task_id: str, title: str, score: float, reason: str) -> None:
        """Log a candidate that was filtered out with the reason."""
        self.emit(AgentEvent(
            module="Discovery", family="valuation", event_name="candidate_filtered_out",
            task_id=task_id,
            detail=f"score={score:.3f} │ {title[:50]}",
            reasoning=reason,
            success=False,
            data={
                "candidate_id": task_id,
                "score": score,
                "title": title,
                "filtered_reason": reason,
            },
        ))

    def discover_summary(self, raw: int, after_heuristic: int, after_llm: int, final: int) -> None:
        """Log the full discovery funnel in one event."""
        self.emit(AgentEvent(
            module="Discovery", family="funnel", event_name="funnel_summarized",
            detail=f"raw={raw} → heuristic={after_heuristic} → llm={after_llm} → final={final}",
            data={
                "raw_candidates": raw,
                "after_heuristic": after_heuristic,
                "after_llm": after_llm,
                "queued": final,
            },
        ))

    def experience_injected(self, task_id: str, count: int, summaries: str) -> None:
        """Log which past experiences were injected into planning."""
        self.emit(AgentEvent(
            module="Memory", family="recall", event_name="experience_injected",
            task_id=task_id,
            detail=f"{count} experiences",
            reasoning=summaries[:200],
            data={
                "injected_count": count,
                "summary_preview": summaries[:200],
            },
        ))

    def value_assessed(self, task_id: str, title: str, score: float, recommendation: str) -> None:
        ok = recommendation == "execute"
        self.emit(AgentEvent(
            task_id=task_id,
            module="Discovery", family="valuation", event_name="value_assessed",
            detail=f"score={score:.2f} {recommendation} │ {title[:60]}",
            success=ok,
            data={
                "candidate_id": task_id,
                "score": score,
                "decision": recommendation,
                "title": title,
            },
        ))

    def task_queued(self, task_id: str, title: str, source: str) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            detail=f"{title[:50]} (source={source})",
            module="Discovery", family="queue", event_name="candidate_queued",
            data={
                "source": source,
                "title": title,
            },
        ))

    def plan_started(self, task_id: str, title: str) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="planning", event_name="plan_started",
            detail=title[:60],
            data={"title": title},
        ))

    def plan_created(self, task_id: str, step_count: int, commit_msg: str) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="planning", event_name="plan_created",
            detail=f"{step_count} steps │ {commit_msg[:50]}",
            success=True,
            data={
                "step_count": step_count,
                "commit_message": commit_msg,
            },
        ))

    def replan_triggered(self, task_id: str, round_number: int, trigger: str) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="planning", event_name="replan_triggered",
            detail=f"round={round_number} trigger={trigger}",
            data={"round": round_number, "trigger": trigger},
        ))

    def replan_created(self, task_id: str, round_number: int, step_count: int) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="planning", event_name="replan_created",
            detail=f"round={round_number} steps={step_count}",
            success=True,
            data={"round": round_number, "step_count": step_count},
        ))

    def replan_exhausted(self, task_id: str, total_rounds: int) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="planning", event_name="replan_exhausted",
            detail=f"exhausted after {total_rounds} rounds",
            success=False,
            data={"round": total_rounds},
        ))

    def plan_blocked(self, task_id: str, reason: str) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="planning", event_name="plan_blocked",
            detail=reason, success=False,
            data={"blocked_reason": reason},
        ))

    def execute_step(self, task_id: str, step_index: int, total: int, action: str, target: str, success: bool, output: str = "") -> None:
        tool_type = _tool_type_for_action(action)
        self.emit(AgentEvent(
            module="Execution",
            family="tool_call",
            event_name="tool_call_succeeded" if success else "tool_call_failed",
            task_id=task_id,
            detail=f"{action} {target}" + (f" │ {output[:80]}" if output and not success else ""),
            success=success,
            data={
                "step_id": f"step-{step_index + 1}",
                "tool_call_id": f"{task_id}-step-{step_index + 1}",
                "tool_type": tool_type,
                "tool_name": action,
                "target": target,
                "output_summary": output[:80] if output else "",
                "step_index": step_index + 1,
                "step_total": total,
            },
        ))

    def execute_finished(self, task_id: str, all_ok: bool) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="state", event_name="execution_completed",
            detail="all steps passed" if all_ok else "one or more steps failed",
            success=all_ok,
            data={"completion_kind": "success" if all_ok else "failure"},
        ))

    def verify_result(self, task_id: str, passed: bool, summary: str) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="verification", event_name="verification_completed",
            detail=summary[:100], success=passed,
            data={"summary": summary[:100]},
        ))

    def git_worktree(self, task_id: str, branch: str, success: bool) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="tool_call",
            event_name="tool_call_succeeded" if success else "tool_call_failed",
            detail=f"branch={branch}", success=success,
            data={
                "tool_type": "git",
                "tool_name": "git_create_worktree",
                "branch_name": branch,
            },
        ))

    def git_committed(self, task_id: str, message: str) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="tool_call", event_name="tool_call_succeeded",
            detail=message[:60], success=True,
            data={
                "tool_type": "git",
                "tool_name": "git_commit",
                "commit_message": message,
            },
        ))

    def git_pushed(self, task_id: str) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="tool_call", event_name="tool_call_succeeded",
            success=True,
            data={
                "tool_type": "git",
                "tool_name": "git_push",
            },
        ))

    def git_pr(self, task_id: str, url: str, success: bool) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="tool_call",
            event_name="tool_call_succeeded" if success else "tool_call_failed",
            detail=url[:120], success=success,
            data={
                "tool_type": "git",
                "tool_name": "git_create_pr",
                "pr_url": url,
            },
        ))

    def task_completed(self, task_id: str, title: str) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="state", event_name="task_completed",
            detail=title[:60], success=True,
            data={"title": title, "to_status": "completed"},
        ))

    def task_failed(self, task_id: str, reason: str) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="state", event_name="task_failed",
            detail=reason[:120], success=False,
            data={"blocked_reason": reason, "to_status": "failed"},
        ))

    def task_needs_human(self, task_id: str, reason: str) -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="Execution", family="state", event_name="task_needs_human",
            detail=reason[:120], success=False,
            data={"blocked_reason": reason, "to_status": "needs_human"},
        ))

    def decision(self, description: str, reasoning: str, task_id: str = "") -> None:
        self.emit(AgentEvent(
            task_id=task_id,
            module="LLM", family="audit_link", event_name="decision_recorded",
            detail=description, reasoning=reasoning,
            data={"description": description},
        ))

    def llm_tool_selection(
        self,
        *,
        task_id: str,
        model: str,
        tool_names: list[str],
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> None:
        detail = ", ".join(tool_names[:4]) if tool_names else "no tools"
        if len(tool_names) > 4:
            detail = f"{detail}, +{len(tool_names) - 4} more"
        self.emit(AgentEvent(
            task_id=task_id,
            module="LLM",
            family="tool_selection",
            event_name="tool_selection_recorded",
            detail=f"{detail} | in={prompt_tokens} out={completion_tokens} total={total_tokens}",
            success=True,
            data={
                "model": model,
                "tool_names": tool_names,
                "tool_count": len(tool_names),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        ))

    def system_event(self, action: str, detail: str = "", success: Optional[bool] = None) -> None:
        self.emit(AgentEvent(
            module="ControlPlane", family="runtime", event_name=action,
            detail=detail, success=success,
        ))

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

    def find(self, module: str = "", family: str = "", event_name: str = "") -> List[AgentEvent]:
        return [
            e for e in self.events
            if (not module or e.module == module)
            and (not family or e.family == family)
            and (not event_name or e.event_name == event_name)
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


def _phase_from_module(module: str) -> str:
    return MODULE_TO_PHASE.get(module, module.lower())


def _module_from_phase(phase: str) -> str:
    return PHASE_TO_MODULE.get(phase, phase.upper())


def _family_from_action(action: str) -> str:
    if action.startswith("step ["):
        return "tool_call"
    return ACTION_TO_FAMILY.get(action, "general")


def _tool_type_for_action(action: str) -> str:
    if action.startswith(("edit_", "create_", "read_", "write_", "delete_", "list_", "search_")):
        return "filesystem"
    if action.startswith(("run_", "exec_")) or action in {"pytest", "npm", "make"}:
        return "command"
    if action.startswith("git_"):
        return "git"
    return "other"


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

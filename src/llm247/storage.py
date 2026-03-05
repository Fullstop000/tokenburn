from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


class TaskStateStore:
    """Persist and load each task's last successful run timestamp."""

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path

    def get_last_run(self, task_name: str) -> Optional[datetime]:
        """Return the last run timestamp for a task or None if absent."""
        state = self._load_state()
        task_state = state.get(task_name)
        if task_state is None:
            return None

        try:
            return datetime.fromisoformat(task_state["last_run_at"])
        except ValueError:
            return None

    def get_run_count(self, task_name: str) -> int:
        """Return successful run count for one task."""
        state = self._load_state()
        task_state = state.get(task_name)
        if task_state is None:
            return 0
        return int(task_state.get("run_count", 0))

    def get_total_duration_seconds(self, task_name: str) -> float:
        """Return cumulative successful execution duration for one task."""
        state = self._load_state()
        task_state = state.get(task_name)
        if task_state is None:
            return 0.0
        return float(task_state.get("total_duration_seconds", 0.0))

    def mark_run(self, task_name: str, run_at: datetime, duration_seconds: float = 0.0) -> None:
        """Record latest successful run metadata and persist to disk."""
        state = self._load_state()
        previous = state.get(task_name, _default_task_state())
        normalized_duration = max(0.0, float(duration_seconds))
        state[task_name] = {
            "last_run_at": run_at.isoformat(),
            "run_count": int(previous.get("run_count", 0)) + 1,
            "total_duration_seconds": float(previous.get("total_duration_seconds", 0.0)) + normalized_duration,
        }
        self._write_state(state)

    def _load_state(self) -> Dict[str, Dict[str, object]]:
        """Load and normalize on-disk state with compatibility fallback."""
        if not self.state_path.exists():
            return {}

        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            return _normalize_state(data)
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_state(self, state: Dict[str, Dict[str, object]]) -> None:
        """Safely flush state to disk using atomic file replacement."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(state, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(self.state_path)


def _default_task_state() -> Dict[str, object]:
    """Return default normalized shape for one task state item."""
    return {
        "last_run_at": "",
        "run_count": 0,
        "total_duration_seconds": 0.0,
    }


def _normalize_state(raw_state: Dict[object, object]) -> Dict[str, Dict[str, object]]:
    """Normalize legacy/new state payloads into one stable in-memory schema."""
    normalized: Dict[str, Dict[str, object]] = {}
    for raw_key, raw_value in raw_state.items():
        key = str(raw_key)
        if isinstance(raw_value, str):
            normalized[key] = {
                "last_run_at": raw_value,
                "run_count": 1,
                "total_duration_seconds": 0.0,
            }
            continue

        if isinstance(raw_value, dict):
            last_run_at = str(raw_value.get("last_run_at", ""))
            run_count = int(raw_value.get("run_count", 0))
            total_duration_seconds = float(raw_value.get("total_duration_seconds", 0.0))
            if last_run_at and run_count <= 0:
                run_count = 1
            normalized[key] = {
                "last_run_at": last_run_at,
                "run_count": max(0, run_count),
                "total_duration_seconds": max(0.0, total_duration_seconds),
            }
            continue

        normalized[key] = _default_task_state()

    return normalized

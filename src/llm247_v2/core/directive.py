from __future__ import annotations

import json
from pathlib import Path

from llm247_v2.core.models import Directive, TaskSourceConfig


def default_directive() -> Directive:
    return Directive(
        paused=False,
        focus_areas=["code_quality", "testing", "documentation"],
        forbidden_paths=[".env", ".git", "credentials.json"],
        max_file_changes_per_task=10,
        custom_instructions="",
        task_sources={
            "todo_scan": TaskSourceConfig(enabled=True, priority=2),
            "test_gap": TaskSourceConfig(enabled=True, priority=1),
            "self_improvement": TaskSourceConfig(enabled=True, priority=3),
            "lint_check": TaskSourceConfig(enabled=True, priority=2),
        },
        poll_interval_seconds=120,
        max_steps=50,
        max_tokens_per_task=0,
    )


def load_directive(path: Path) -> Directive:
    if not path.exists():
        return default_directive()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default_directive()

        sources: dict[str, TaskSourceConfig] = {}
        for key, val in data.get("task_sources", {}).items():
            if isinstance(val, dict):
                sources[key] = TaskSourceConfig(
                    enabled=bool(val.get("enabled", True)),
                    priority=int(val.get("priority", 3)),
                )

        return Directive(
            paused=bool(data.get("paused", False)),
            focus_areas=data.get("focus_areas", []),
            forbidden_paths=data.get("forbidden_paths", [".env", ".git"]),
            max_file_changes_per_task=int(data.get("max_file_changes_per_task", 10)),
            custom_instructions=str(data.get("custom_instructions", "")),
            task_sources=sources or default_directive().task_sources,
            poll_interval_seconds=int(data.get("poll_interval_seconds", 120)),
            max_steps=int(data.get("max_steps", data.get("max_replan_rounds", 50))),
            max_tokens_per_task=int(data.get("max_tokens_per_task", 0)),
        )
    except (json.JSONDecodeError, OSError, ValueError):
        return default_directive()


def save_directive(path: Path, directive: Directive) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sources_raw = {}
    for key, cfg in directive.task_sources.items():
        sources_raw[key] = {"enabled": cfg.enabled, "priority": cfg.priority}

    payload = {
        "paused": directive.paused,
        "focus_areas": directive.focus_areas,
        "forbidden_paths": directive.forbidden_paths,
        "max_file_changes_per_task": directive.max_file_changes_per_task,
        "custom_instructions": directive.custom_instructions,
        "task_sources": sources_raw,
        "poll_interval_seconds": directive.poll_interval_seconds,
        "max_steps": directive.max_steps,
        "max_tokens_per_task": directive.max_tokens_per_task,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def directive_to_prompt_section(directive: Directive) -> str:
    """Render directive as a prompt section for LLM context."""
    lines = ["## Agent Directive (Behavior Control)"]
    if directive.focus_areas:
        lines.append(f"Focus areas: {', '.join(directive.focus_areas)}")
    if directive.forbidden_paths:
        lines.append(f"Forbidden paths: {', '.join(directive.forbidden_paths)}")
    lines.append(f"Max file changes per task: {directive.max_file_changes_per_task}")
    if directive.custom_instructions:
        lines.append(f"Custom instructions: {directive.custom_instructions}")

    enabled_sources = [k for k, v in directive.task_sources.items() if v.enabled]
    if enabled_sources:
        lines.append(f"Enabled task sources: {', '.join(enabled_sources)}")

    return "\n".join(lines)

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import List

from llm247_v2.core.constitution import Constitution
from llm247_v2.core.directive import directive_to_prompt_section
from llm247_v2.llm.client import LLMClient, extract_json
from llm247_v2.core.models import Directive, PlanStep, Task, TaskPlan
from llm247_v2.llm.prompts import render as render_prompt

logger = logging.getLogger("llm247_v2.execution.planner")


def plan_task_with_constitution(
    task: Task,
    workspace: Path,
    directive: Directive,
    constitution: Constitution,
    llm: LLMClient,
    experience_context: str = "",
) -> TaskPlan:
    """Generate an execution plan governed by constitution, directive, and past experience."""
    prompt = render_prompt(
        "plan_task",
        constitution_section=constitution.to_compact_prompt(),
        task_title=task.title,
        task_description=task.description,
        task_source=task.source,
        experience_section=f"{experience_context}\n" if experience_context else "",
        directive_section=directive_to_prompt_section(directive),
        repo_context=_read_relevant_files(workspace, task),
        max_file_changes=str(directive.max_file_changes_per_task),
    )

    return _call_and_parse_plan(llm, prompt, task, directive)


def plan_task(task: Task, workspace: Path, directive: Directive, llm: LLMClient) -> TaskPlan:
    """Legacy entry point without constitution — for backward compatibility."""
    from llm247_v2.core.constitution import _default_constitution
    return plan_task_with_constitution(task, workspace, directive, _default_constitution(), llm)


def _call_and_parse_plan(llm: LLMClient, prompt: str, task: Task, directive: Directive) -> TaskPlan:
    """Call LLM with planning prompt and parse the response."""
    try:
        raw = llm.generate(prompt)
    except Exception:
        logger.exception("LLM planning failed for task %s", task.id)
        return _fallback_plan(task)

    parsed = extract_json(raw)
    if not parsed:
        logger.warning("Failed to parse plan JSON for task %s", task.id)
        return _fallback_plan(task)

    steps: List[PlanStep] = []
    for item in parsed.get("steps", []):
        if not isinstance(item, dict):
            continue
        action = str(item.get("action", "")).strip()
        target = str(item.get("target", "")).strip()
        if not action or not target:
            continue
        steps.append(PlanStep(
            action=action,
            target=target,
            content=str(item.get("content", "")),
            description=str(item.get("description", "")),
        ))

    if not steps:
        return _fallback_plan(task)

    return TaskPlan(
        task_id=task.id,
        steps=steps[:directive.max_file_changes_per_task + 2],
        commit_message=str(parsed.get("commit_message", f"feat: {task.title}")),
        pr_title=str(parsed.get("pr_title", task.title)),
        pr_body=str(parsed.get("pr_body", f"Auto-generated for: {task.title}\n\n{task.description}")),
    )


def serialize_plan(plan: TaskPlan) -> str:
    """Serialize plan to JSON string for storage."""
    return json.dumps({
        "task_id": plan.task_id,
        "steps": [
            {"action": s.action, "target": s.target, "content": s.content, "description": s.description}
            for s in plan.steps
        ],
        "commit_message": plan.commit_message,
        "pr_title": plan.pr_title,
        "pr_body": plan.pr_body,
    }, ensure_ascii=False)


def deserialize_plan(raw: str) -> TaskPlan | None:
    """Deserialize plan from JSON string."""
    try:
        data = json.loads(raw)
        steps = [
            PlanStep(
                action=s["action"],
                target=s["target"],
                content=s.get("content", ""),
                description=s.get("description", ""),
            )
            for s in data.get("steps", [])
        ]
        return TaskPlan(
            task_id=data.get("task_id", ""),
            steps=steps,
            commit_message=data.get("commit_message", ""),
            pr_title=data.get("pr_title", ""),
            pr_body=data.get("pr_body", ""),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _fallback_plan(task: Task) -> TaskPlan:
    """Return an empty plan so the agent skips execution rather than wasting tokens on a useless step."""
    logger.warning("Using empty fallback plan for task %s — LLM failed to produce a valid plan", task.id)
    return TaskPlan(
        task_id=task.id,
        steps=[],
        commit_message="",
        pr_title=task.title,
        pr_body="",
    )


def _read_relevant_files(workspace: Path, task: Task) -> str:
    """Read files mentioned in task description for planning context."""
    parts: List[str] = []

    file_refs = re.findall(r"[\w/]+\.py", task.description)
    for ref in file_refs[:5]:
        path = workspace / ref
        if path.exists() and path.stat().st_size < 50_000:
            try:
                content = path.read_text(encoding="utf-8")
                parts.append(f"### {ref}\n```python\n{content[:3000]}\n```")
            except OSError:
                continue

    if not parts:
        parts.append("(No specific files referenced in task)")

    return "\n\n".join(parts)

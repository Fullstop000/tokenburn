from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from llm247_v2.core.constitution import Constitution
from llm247_v2.llm.client import LLMClient, extract_json
from llm247_v2.core.models import Directive, Task
from llm247_v2.llm.prompts import render as render_prompt

logger = logging.getLogger("llm247_v2.discovery.value")


@dataclass(frozen=True)
class ValueDimension:
    name: str
    score: float
    reason: str


@dataclass(frozen=True)
class TaskValue:
    task_id: str
    total_score: float
    dimensions: list[ValueDimension]
    recommendation: str
    should_execute: bool


def assess_task_value_heuristic(task: Task, directive: Directive) -> TaskValue:
    """Fast heuristic-based value assessment — no LLM call."""
    dims: list[ValueDimension] = []

    dims.append(_score_severity(task))
    dims.append(_score_alignment(task, directive))
    dims.append(_score_scope(task))
    dims.append(_score_actionability(task))

    total = sum(d.score for d in dims) / len(dims) if dims else 0
    should_execute = total >= 0.3

    return TaskValue(
        task_id=task.id,
        total_score=round(total, 3),
        dimensions=dims,
        recommendation="execute" if should_execute else "skip",
        should_execute=should_execute,
    )


def assess_tasks_with_llm(
    tasks: List[Task],
    constitution: Constitution,
    directive: Directive,
    llm: LLMClient,
) -> List[TaskValue]:
    """LLM-based deep value assessment for final ranking of top candidates."""
    if not tasks:
        return []

    task_descriptions = "\n".join(
        f"- [{t.id[:8]}] (source={t.source}, priority={t.priority}) {t.title}: {t.description[:150]}"
        for t in tasks[:10]
    )

    prompt = render_prompt(
        "assess_value",
        mission=constitution.mission[:200],
        principles="; ".join(constitution.principles[:3]),
        focus=", ".join(directive.focus_areas) if directive.focus_areas else "general quality",
        custom_instructions=directive.custom_instructions[:200],
        task_descriptions=task_descriptions,
    )

    try:
        raw = llm.generate(prompt)
    except Exception:
        logger.exception("LLM value assessment failed")
        return [assess_task_value_heuristic(t, directive) for t in tasks]

    parsed = extract_json(raw)
    if not parsed or not isinstance(parsed.get("assessments"), list):
        return [assess_task_value_heuristic(t, directive) for t in tasks]

    task_map = {t.id: t for t in tasks}
    results: list[TaskValue] = []

    for item in parsed["assessments"]:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("id", ""))
        matched_task = task_map.get(task_id)
        if not matched_task:
            for tid in task_map:
                if tid.startswith(task_id):
                    matched_task = task_map[tid]
                    task_id = tid
                    break
        if not matched_task:
            continue

        dims = [
            ValueDimension("impact", _clamp(item.get("impact", 0.5)), "LLM assessed"),
            ValueDimension("feasibility", _clamp(item.get("feasibility", 0.5)), "LLM assessed"),
            ValueDimension("risk", _clamp(item.get("risk", 0.5)), "LLM assessed"),
            ValueDimension("alignment", _clamp(item.get("alignment", 0.5)), "LLM assessed"),
        ]
        total = sum(d.score for d in dims) / len(dims)
        rec = str(item.get("recommendation", "execute"))
        should_exec = rec == "execute" and total >= 0.4

        results.append(TaskValue(
            task_id=task_id,
            total_score=round(total, 3),
            dimensions=dims,
            recommendation=rec,
            should_execute=should_exec,
        ))

    assessed_ids = {v.task_id for v in results}
    for t in tasks:
        if t.id not in assessed_ids:
            results.append(assess_task_value_heuristic(t, directive))

    return results


def rank_and_filter(
    tasks: List[Task],
    values: List[TaskValue],
    max_tasks: int = 5,
) -> List[Task]:
    """Rank tasks by value score and filter out low-value ones."""
    value_map = {v.task_id: v for v in values}

    scored = []
    for t in tasks:
        v = value_map.get(t.id)
        score = v.total_score if v else 0.0
        should = v.should_execute if v else False
        if should:
            scored.append((score, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:max_tasks]]


def should_skip_discovery(queued_count: int, threshold: int = 5) -> bool:
    """If queue already has enough tasks, skip discovery to save tokens."""
    return queued_count >= threshold


def format_value_log(values: List[TaskValue]) -> str:
    """Render value assessments for audit trail."""
    lines: list[str] = []
    for v in sorted(values, key=lambda x: x.total_score, reverse=True):
        dims_str = " | ".join(f"{d.name}={d.score:.2f}" for d in v.dimensions)
        lines.append(f"[{v.task_id[:8]}] score={v.total_score:.3f} rec={v.recommendation} ({dims_str})")
    return "\n".join(lines)


def _score_severity(task: Task) -> ValueDimension:
    source = task.source
    title_lower = task.title.lower()

    if source == "lint_check" or "syntax error" in title_lower:
        return ValueDimension("severity", 0.95, "Syntax errors are critical")
    if "fixme" in title_lower or "bug" in title_lower:
        return ValueDimension("severity", 0.8, "Bug/FIXME is high severity")
    if source == "test_gap":
        return ValueDimension("severity", 0.7, "Missing tests are important")
    if "todo" in title_lower:
        return ValueDimension("severity", 0.5, "TODO is medium severity")
    if source == "self_improvement":
        return ValueDimension("severity", 0.4, "Improvement is lower urgency")
    return ValueDimension("severity", 0.3, "Default severity")


def _score_alignment(task: Task, directive: Directive) -> ValueDimension:
    if not directive.focus_areas:
        return ValueDimension("alignment", 0.5, "No focus areas configured")

    combined = (task.title + " " + task.description + " " + task.source).lower()
    matches = sum(1 for area in directive.focus_areas if _fuzzy_match(area.lower(), combined))

    if matches >= 2:
        return ValueDimension("alignment", 0.95, f"Matches {matches} focus areas")
    if matches == 1:
        return ValueDimension("alignment", 0.7, "Matches 1 focus area")
    return ValueDimension("alignment", 0.2, "No focus area match")


def _score_scope(task: Task) -> ValueDimension:
    desc_len = len(task.description)
    if desc_len < 50:
        return ValueDimension("scope", 0.3, "Too vague, minimal description")
    if desc_len < 300:
        return ValueDimension("scope", 0.8, "Well-scoped task")
    if desc_len < 800:
        return ValueDimension("scope", 0.6, "Moderate scope")
    return ValueDimension("scope", 0.4, "Very large scope, may need splitting")


def _score_actionability(task: Task) -> ValueDimension:
    desc = task.description.lower()
    has_file_ref = ".py" in desc or ".md" in desc or ".txt" in desc
    has_location = "line" in desc or ":" in task.title

    if has_file_ref and has_location:
        return ValueDimension("actionability", 0.9, "Specific file and location")
    if has_file_ref:
        return ValueDimension("actionability", 0.7, "References specific files")
    if task.source in ("todo_scan", "lint_check"):
        return ValueDimension("actionability", 0.6, "Source implies concrete location")
    return ValueDimension("actionability", 0.3, "Abstract, no concrete target")


def _fuzzy_match(keyword: str, text: str) -> bool:
    """Check if keyword (or its stem) appears in text."""
    if keyword in text:
        return True
    stem = keyword.rstrip("s").rstrip("ing").rstrip("tion").rstrip("e")
    if len(stem) >= 3 and stem in text:
        return True
    return False


def _clamp(val, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(val)))
    except (TypeError, ValueError):
        return 0.5

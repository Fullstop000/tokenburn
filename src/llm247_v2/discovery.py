from __future__ import annotations

import hashlib
import logging
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from llm247_v2.constitution import Constitution
from llm247_v2.prompts import render as render_prompt
from llm247_v2.exploration import (
    ExplorationMap,
    Strategy,
    build_deep_review_context,
    record_strategy_result,
    scan_change_hotspots,
    scan_complexity,
    scan_stale_areas,
    select_strategy,
)
from llm247_v2.interest import (
    InterestProfile,
    build_interest_profile,
    discover_dep_vulnerabilities,
    discover_github_issues,
    discover_interest_driven,
    discover_web_search,
)
from llm247_v2.llm_client import LLMClient, extract_json
from llm247_v2.models import Directive, Task, TaskSource, TaskStatus
from llm247_v2.value import (
    TaskValue,
    assess_task_value_heuristic,
    assess_tasks_with_llm,
    format_value_log,
    rank_and_filter,
    should_skip_discovery,
)

if TYPE_CHECKING:
    from llm247_v2.observer import Observer

logger = logging.getLogger("llm247_v2.discovery")


def discover_and_evaluate(
    workspace: Path,
    directive: Directive,
    constitution: Constitution,
    llm: LLMClient,
    emap: ExplorationMap,
    existing_titles: set[str],
    queued_count: int,
    observer: Optional["Observer"] = None,
    interest_profile: Optional[InterestProfile] = None,
) -> tuple[List[Task], str]:
    """Full discovery pipeline: explore → collect → evaluate → rank.

    Returns (ranked_tasks, discovery_log).
    """
    log_parts: list[str] = []

    if should_skip_discovery(queued_count):
        msg = f"Skipping discovery: {queued_count} tasks already queued"
        logger.info(msg)
        return [], msg

    strategy = select_strategy(emap, directive, constitution, queued_count)
    log_parts.append(f"Strategy: {strategy.name} ({strategy.description})")
    logger.info("Discovery strategy: %s", strategy.name)

    raw_tasks = _execute_strategy(workspace, directive, constitution, llm, strategy, emap, existing_titles, interest_profile)
    log_parts.append(f"Raw candidates: {len(raw_tasks)}")

    if observer and raw_tasks:
        observer.discover_raw_candidates([
            {"id": t.id, "title": t.title, "source": t.source}
            for t in raw_tasks
        ])

    if not raw_tasks:
        record_strategy_result(emap, strategy.name, strategy.target_areas, 0)
        return [], "\n".join(log_parts)

    heuristic_values = [assess_task_value_heuristic(t, directive) for t in raw_tasks]

    if observer:
        _emit_value_events(observer, raw_tasks, heuristic_values, stage="heuristic")

    pre_filtered = rank_and_filter(raw_tasks, heuristic_values, max_tasks=10)
    log_parts.append(f"After heuristic filter: {len(pre_filtered)}")

    if observer:
        _emit_filtered_out(observer, raw_tasks, heuristic_values, pre_filtered, reason="heuristic score too low")

    after_llm = len(pre_filtered)
    if len(pre_filtered) > 3:
        llm_values = assess_tasks_with_llm(pre_filtered, constitution, directive, llm)

        if observer:
            _emit_value_events(observer, pre_filtered, llm_values, stage="llm")

        final_tasks = rank_and_filter(pre_filtered, llm_values, max_tasks=5)
        after_llm = len(final_tasks)
        log_parts.append(f"After LLM value assessment: {len(final_tasks)}")
        log_parts.append(format_value_log(llm_values))

        if observer:
            _emit_filtered_out(observer, pre_filtered, llm_values, final_tasks, reason="LLM assessment: low value or skip recommendation")
    else:
        final_tasks = pre_filtered
        log_parts.append(format_value_log(heuristic_values))

    if observer:
        observer.discover_summary(
            raw=len(raw_tasks),
            after_heuristic=len(pre_filtered),
            after_llm=after_llm,
            final=len(final_tasks),
        )

    record_strategy_result(emap, strategy.name, strategy.target_areas, len(final_tasks))

    return final_tasks, "\n".join(log_parts)


def _emit_value_events(observer: "Observer", tasks: List[Task], values: List[TaskValue], stage: str) -> None:
    value_map = {v.task_id: v for v in values}
    for t in tasks:
        v = value_map.get(t.id)
        if not v:
            continue
        dims_str = ", ".join(f"{d.name}={d.score:.2f}" for d in v.dimensions)
        observer.discover_value_scored(
            t.id, t.title, v.total_score, v.recommendation,
            dimensions=f"[{stage}] {dims_str}",
        )


def _emit_filtered_out(
    observer: "Observer",
    all_tasks: List[Task],
    values: List[TaskValue],
    kept_tasks: List[Task],
    reason: str,
) -> None:
    kept_ids = {t.id for t in kept_tasks}
    value_map = {v.task_id: v for v in values}
    for t in all_tasks:
        if t.id not in kept_ids:
            v = value_map.get(t.id)
            score = v.total_score if v else 0.0
            observer.discover_filtered_out(t.id, t.title, score, reason)


def _execute_strategy(
    workspace: Path,
    directive: Directive,
    constitution: Constitution,
    llm: LLMClient,
    strategy: Strategy,
    emap: ExplorationMap,
    existing: set[str],
    interest_profile: Optional[InterestProfile] = None,
) -> List[Task]:
    """Dispatch to the appropriate scanning function based on strategy."""
    name = strategy.name

    if name == "todo_sweep":
        return _scan_todos(workspace, existing)

    if name == "test_coverage":
        return _scan_test_gaps(workspace, existing)

    if name == "change_hotspot":
        return _scan_hotspots(workspace, existing)

    if name == "complexity_scan":
        return _scan_complexity_tasks(workspace, existing)

    if name == "stale_area":
        return _scan_stale_area_tasks(workspace, emap, directive, constitution, llm, existing)

    if name == "deep_module_review":
        return _deep_review(workspace, emap, directive, constitution, llm, existing)

    if name == "dependency_review":
        return _scan_dependency_tasks(workspace, existing)

    if name == "llm_guided":
        return _llm_guided_discovery(workspace, directive, constitution, llm, existing)

    if name == "github_issues":
        return discover_github_issues(workspace, existing)

    if name == "dep_audit":
        return discover_dep_vulnerabilities(workspace, existing)

    if name == "web_search":
        ip = interest_profile or build_interest_profile(directive)
        return discover_web_search(workspace, directive, llm, ip, existing)

    if name == "interest_driven":
        ip = interest_profile or build_interest_profile(directive)
        return discover_interest_driven(workspace, llm, ip, existing)

    logger.warning("Unknown strategy: %s, falling back to todo_sweep", name)
    return _scan_todos(workspace, existing)


def _scan_todos(workspace: Path, existing: set[str]) -> List[Task]:
    """Scan for TODO/FIXME/HACK/BUG. ID is based on content, not line number."""
    tasks: List[Task] = []
    pattern = r"(TODO|FIXME|HACK|BUG|XXX)\b"

    try:
        result = subprocess.run(
            ["rg", "--no-heading", "-n", "-i", pattern, "--type", "py", "--type", "md"],
            cwd=workspace, capture_output=True, text=True, timeout=30,
        )
        lines = result.stdout.strip().splitlines()[:50]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return tasks

    for line in lines:
        match = re.match(r"^(.+?):(\d+):(.+)$", line)
        if not match:
            continue

        filepath, lineno, content = match.group(1), match.group(2), match.group(3).strip()
        tag = _extract_tag(content)
        clean_content = re.sub(r"#\s*(TODO|FIXME|HACK|BUG|XXX)\s*[:：]?\s*", "", content, flags=re.I).strip()
        title = f"Resolve {tag} in {filepath}: {clean_content[:60]}"

        if title in existing:
            continue

        task_id = _make_id("todo", filepath, clean_content[:80])
        tasks.append(Task(
            id=task_id,
            title=title,
            description=f"File: {filepath}\nLine: {lineno}\nContent: {content}",
            source=TaskSource.TODO_SCAN.value,
            status=TaskStatus.DISCOVERED.value,
            priority=2 if tag in ("BUG", "FIXME") else 3,
        ))

    return tasks[:10]


def _scan_test_gaps(workspace: Path, existing: set[str]) -> List[Task]:
    tasks: List[Task] = []
    src_dir = workspace / "src"
    test_dir = workspace / "tests"
    if not src_dir.exists() or not test_dir.exists():
        return tasks

    test_files = {p.name for p in test_dir.rglob("test_*.py")}

    for py_file in src_dir.rglob("*.py"):
        if py_file.name.startswith("_"):
            continue
        expected_test = f"test_{py_file.name}"
        if expected_test not in test_files:
            rel = str(py_file.relative_to(workspace))
            title = f"Add tests for {rel}"
            if title in existing:
                continue
            tasks.append(Task(
                id=_make_id("test_gap", rel),
                title=title,
                description=f"Module {rel} has no corresponding test file ({expected_test}).",
                source=TaskSource.TEST_GAP.value,
                status=TaskStatus.DISCOVERED.value,
                priority=2,
            ))

    return tasks[:5]


def _scan_hotspots(workspace: Path, existing: set[str]) -> List[Task]:
    """Create tasks from frequently-changed files."""
    hotspots = scan_change_hotspots(workspace, limit=10)
    tasks: List[Task] = []

    for h in hotspots:
        if h["changes"] < 3:
            continue
        filepath = h["file"]
        title = f"Review change hotspot: {filepath} ({h['changes']} changes)"
        if title in existing:
            continue
        tasks.append(Task(
            id=_make_id("hotspot", filepath),
            title=title,
            description=(
                f"File {filepath} has been modified {h['changes']} times in recent history.\n"
                "Frequent changes may indicate design issues, unclear responsibilities, or missing abstractions."
            ),
            source=TaskSource.SELF_IMPROVEMENT.value,
            status=TaskStatus.DISCOVERED.value,
            priority=3,
        ))

    return tasks[:5]


def _scan_complexity_tasks(workspace: Path, existing: set[str]) -> List[Task]:
    findings = scan_complexity(workspace, max_lines=300)
    tasks: List[Task] = []

    for f in findings:
        title = f"Reduce complexity: {f['issue']}"
        if title in existing:
            continue
        tasks.append(Task(
            id=_make_id("complexity", f["file"], f["issue"]),
            title=title,
            description=f"File: {f['file']}\n{f['issue']}",
            source=TaskSource.SELF_IMPROVEMENT.value,
            status=TaskStatus.DISCOVERED.value,
            priority=4,
        ))

    return tasks[:5]


def _scan_stale_area_tasks(
    workspace: Path,
    emap: ExplorationMap,
    directive: Directive,
    constitution: Constitution,
    llm: LLMClient,
    existing: set[str],
) -> List[Task]:
    """Explore under-visited areas with LLM analysis."""
    stale = scan_stale_areas(workspace, emap)
    if not stale:
        return _scan_todos(workspace, existing)

    target = stale[0]
    prompt = render_prompt(
        "discover_stale_area",
        constitution_section=constitution.to_compact_prompt(),
        target=target,
        focus=", ".join(directive.focus_areas) if directive.focus_areas else "code quality",
        code_context=build_deep_review_context(workspace, target, max_bytes=6000),
    )

    return _parse_llm_tasks(llm, prompt, TaskSource.SELF_IMPROVEMENT.value, existing)


def _deep_review(
    workspace: Path,
    emap: ExplorationMap,
    directive: Directive,
    constitution: Constitution,
    llm: LLMClient,
    existing: set[str],
) -> List[Task]:
    """Deep review of one module — read it fully and identify improvements."""
    stale = scan_stale_areas(workspace, emap)
    src_dir = workspace / "src"

    target = stale[0] if stale else "src/"
    if not (workspace / target).exists() and src_dir.exists():
        target = "src/"

    prompt = render_prompt(
        "discover_deep_review",
        constitution_section=constitution.to_compact_prompt(),
        target=target,
        code_context=build_deep_review_context(workspace, target, max_bytes=8000),
    )

    return _parse_llm_tasks(llm, prompt, TaskSource.SELF_IMPROVEMENT.value, existing)


def _scan_dependency_tasks(workspace: Path, existing: set[str]) -> List[Task]:
    """Find files with too many imports (high coupling indicator)."""
    tasks: List[Task] = []
    src_dir = workspace / "src"
    if not src_dir.exists():
        return tasks

    for py_file in src_dir.rglob("*.py"):
        if py_file.name.startswith("_"):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
            import_count = sum(1 for line in content.splitlines() if line.strip().startswith(("import ", "from ")))
            if import_count > 15:
                rel = str(py_file.relative_to(workspace))
                title = f"Review high coupling: {rel} ({import_count} imports)"
                if title in existing:
                    continue
                tasks.append(Task(
                    id=_make_id("coupling", rel),
                    title=title,
                    description=f"{rel} has {import_count} imports, indicating high coupling.",
                    source=TaskSource.SELF_IMPROVEMENT.value,
                    status=TaskStatus.DISCOVERED.value,
                    priority=4,
                ))
        except OSError:
            continue

    return tasks[:5]


def _llm_guided_discovery(
    workspace: Path,
    directive: Directive,
    constitution: Constitution,
    llm: LLMClient,
    existing: set[str],
) -> List[Task]:
    """Fully LLM-driven discovery with rich repo context."""
    custom = directive.custom_instructions or ""
    prompt = render_prompt(
        "discover_llm_guided",
        constitution_section=constitution.to_compact_prompt(),
        focus=", ".join(directive.focus_areas) if directive.focus_areas else "general quality",
        custom_section=f"## Custom Instructions: {custom}" if custom else "",
        repo_context=_build_rich_context(workspace),
    )

    return _parse_llm_tasks(llm, prompt, TaskSource.SELF_IMPROVEMENT.value, existing)


def _parse_llm_tasks(llm: LLMClient, prompt: str, source: str, existing: set[str]) -> List[Task]:
    """Common LLM task parsing with error handling."""
    try:
        raw = llm.generate(prompt)
    except Exception:
        logger.exception("LLM discovery failed")
        return []

    parsed = extract_json(raw)
    if not parsed or not isinstance(parsed.get("tasks"), list):
        return []

    tasks: List[Task] = []
    for item in parsed["tasks"][:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title or title in existing:
            continue
        tasks.append(Task(
            id=_make_id("llm", title),
            title=title,
            description=str(item.get("description", "")),
            source=source,
            status=TaskStatus.DISCOVERED.value,
            priority=min(5, max(1, int(item.get("priority", 3)))),
        ))

    return tasks


def _build_rich_context(workspace: Path) -> str:
    """Build richer context than V1 — includes file content samples."""
    parts: list[str] = []

    try:
        result = subprocess.run(
            ["git", "status", "--short"], cwd=workspace,
            capture_output=True, text=True, timeout=10,
        )
        parts.append(f"### Git Status\n{result.stdout[:1000]}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-15"], cwd=workspace,
            capture_output=True, text=True, timeout=10,
        )
        parts.append(f"### Recent Commits\n{result.stdout[:1500]}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    try:
        result = subprocess.run(
            ["rg", "--files", "--type", "py", "--sort", "modified"], cwd=workspace,
            capture_output=True, text=True, timeout=10,
        )
        parts.append(f"### Python Files\n{result.stdout[:2000]}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    src_dir = workspace / "src"
    if src_dir.exists():
        for py_file in sorted(src_dir.rglob("*.py"))[:5]:
            try:
                content = py_file.read_text(encoding="utf-8")
                rel = str(py_file.relative_to(workspace))
                lines = content.splitlines()
                preview = "\n".join(lines[:30])
                parts.append(f"### {rel} (first 30 lines of {len(lines)})\n```\n{preview}\n```")
            except OSError:
                continue

    return "\n\n".join(parts)


def _extract_tag(content: str) -> str:
    match = re.search(r"(TODO|FIXME|HACK|BUG|XXX)", content, re.IGNORECASE)
    return match.group(1).upper() if match else "TODO"


def _make_id(*parts: str) -> str:
    raw = ":".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]

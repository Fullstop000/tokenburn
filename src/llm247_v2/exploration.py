from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from llm247_v2.constitution import Constitution
from llm247_v2.llm_client import LLMClient, extract_json
from llm247_v2.models import Directive

logger = logging.getLogger("llm247_v2.exploration")


@dataclass
class AreaStatus:
    """Tracking state for one explored area of the codebase."""
    path: str
    last_explored_at: float = 0.0
    explore_count: int = 0
    tasks_found: int = 0
    tasks_completed: int = 0
    file_count: int = 0
    total_lines: int = 0


@dataclass
class ExplorationMap:
    """Persistent map of which parts of the codebase have been explored."""
    areas: Dict[str, AreaStatus] = field(default_factory=dict)
    strategy_history: List[dict] = field(default_factory=list)
    total_cycles: int = 0


class Strategy:
    """One exploration strategy with metadata."""

    def __init__(self, name: str, description: str, target_areas: List[str], depth: str) -> None:
        self.name = name
        self.description = description
        self.target_areas = target_areas
        self.depth = depth  # "shallow" | "medium" | "deep"


BUILTIN_STRATEGIES = {
    "todo_sweep": Strategy(
        name="todo_sweep",
        description="Scan all code for TODO/FIXME/HACK/BUG comments",
        target_areas=["src/"],
        depth="shallow",
    ),
    "test_coverage": Strategy(
        name="test_coverage",
        description="Find modules without corresponding tests",
        target_areas=["src/", "tests/"],
        depth="shallow",
    ),
    "change_hotspot": Strategy(
        name="change_hotspot",
        description="Analyze git log to find frequently-changed files (potential design issues)",
        target_areas=["src/"],
        depth="medium",
    ),
    "stale_area": Strategy(
        name="stale_area",
        description="Explore directories not touched recently",
        target_areas=["src/"],
        depth="medium",
    ),
    "complexity_scan": Strategy(
        name="complexity_scan",
        description="Find overly long functions and files that need refactoring",
        target_areas=["src/"],
        depth="medium",
    ),
    "dependency_review": Strategy(
        name="dependency_review",
        description="Review import relationships and coupling between modules",
        target_areas=["src/"],
        depth="deep",
    ),
    "deep_module_review": Strategy(
        name="deep_module_review",
        description="Pick one under-explored module, read it fully, and identify improvements",
        target_areas=["src/"],
        depth="deep",
    ),
    "llm_guided": Strategy(
        name="llm_guided",
        description="Ask LLM to suggest exploration directions based on repo context",
        target_areas=[],
        depth="deep",
    ),
    "github_issues": Strategy(
        name="github_issues",
        description="Pull open issues from GitHub issue tracker",
        target_areas=[],
        depth="shallow",
    ),
    "dep_audit": Strategy(
        name="dep_audit",
        description="Audit dependencies for known security vulnerabilities",
        target_areas=[],
        depth="medium",
    ),
    "web_search": Strategy(
        name="web_search",
        description="LLM-powered analysis of stack for security advisories, deprecations, and best practices",
        target_areas=[],
        depth="deep",
    ),
    "interest_driven": Strategy(
        name="interest_driven",
        description="Generate tasks driven by the agent's evolved interests and curiosity",
        target_areas=[],
        depth="deep",
    ),
}


def load_exploration_map(path: Path) -> ExplorationMap:
    if not path.exists():
        return ExplorationMap()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        areas = {}
        for key, val in data.get("areas", {}).items():
            areas[key] = AreaStatus(
                path=key,
                last_explored_at=float(val.get("last_explored_at", 0)),
                explore_count=int(val.get("explore_count", 0)),
                tasks_found=int(val.get("tasks_found", 0)),
                tasks_completed=int(val.get("tasks_completed", 0)),
                file_count=int(val.get("file_count", 0)),
                total_lines=int(val.get("total_lines", 0)),
            )
        return ExplorationMap(
            areas=areas,
            strategy_history=data.get("strategy_history", [])[-50:],
            total_cycles=int(data.get("total_cycles", 0)),
        )
    except (json.JSONDecodeError, OSError, ValueError):
        return ExplorationMap()


def save_exploration_map(path: Path, emap: ExplorationMap) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "areas": {
            key: {
                "last_explored_at": s.last_explored_at,
                "explore_count": s.explore_count,
                "tasks_found": s.tasks_found,
                "tasks_completed": s.tasks_completed,
                "file_count": s.file_count,
                "total_lines": s.total_lines,
            }
            for key, s in emap.areas.items()
        },
        "strategy_history": emap.strategy_history[-50:],
        "total_cycles": emap.total_cycles,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def select_strategy(
    emap: ExplorationMap,
    directive: Directive,
    constitution: Constitution,
    queued_task_count: int,
) -> Strategy:
    """Select the best exploration strategy for this cycle."""
    if queued_task_count >= 5:
        return BUILTIN_STRATEGIES["todo_sweep"]

    recent_strategies = [h["strategy"] for h in emap.strategy_history[-5:]]

    stale_areas = _find_stale_areas(emap)
    if stale_areas and "stale_area" not in recent_strategies[-2:]:
        strategy = BUILTIN_STRATEGIES["stale_area"]
        strategy.target_areas = stale_areas[:3]
        return strategy

    high_yield = _find_high_yield_strategy(emap)
    if high_yield and high_yield not in recent_strategies[-3:]:
        return BUILTIN_STRATEGIES.get(high_yield, BUILTIN_STRATEGIES["todo_sweep"])

    if emap.total_cycles % 5 == 0 and emap.total_cycles > 0:
        return BUILTIN_STRATEGIES["deep_module_review"]

    if emap.total_cycles % 7 == 0 and emap.total_cycles > 0:
        return BUILTIN_STRATEGIES["github_issues"]

    if emap.total_cycles % 11 == 0 and emap.total_cycles > 0:
        return BUILTIN_STRATEGIES["dep_audit"]

    if emap.total_cycles % 8 == 0 and emap.total_cycles > 0:
        return BUILTIN_STRATEGIES["web_search"]

    if emap.total_cycles % 6 == 0 and emap.total_cycles > 0:
        if "interest_driven" not in recent_strategies[-3:]:
            return BUILTIN_STRATEGIES["interest_driven"]

    if emap.total_cycles % 3 == 0:
        return BUILTIN_STRATEGIES["change_hotspot"]

    if "complexity_scan" not in recent_strategies[-4:]:
        return BUILTIN_STRATEGIES["complexity_scan"]

    cycle_index = emap.total_cycles % len(BUILTIN_STRATEGIES)
    strategy_names = sorted(BUILTIN_STRATEGIES.keys())
    return BUILTIN_STRATEGIES[strategy_names[cycle_index]]


def record_strategy_result(
    emap: ExplorationMap,
    strategy_name: str,
    areas_explored: List[str],
    tasks_found: int,
) -> None:
    """Update exploration map after a discovery cycle."""
    now = time.time()
    emap.total_cycles += 1

    emap.strategy_history.append({
        "strategy": strategy_name,
        "time": now,
        "areas": areas_explored,
        "tasks_found": tasks_found,
    })

    for area in areas_explored:
        if area not in emap.areas:
            emap.areas[area] = AreaStatus(path=area)
        status = emap.areas[area]
        status.last_explored_at = now
        status.explore_count += 1
        status.tasks_found += tasks_found


def scan_change_hotspots(workspace: Path, limit: int = 10) -> List[dict]:
    """Find files most frequently changed in recent git history."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=", "--name-only", "-50"],
            cwd=workspace, capture_output=True, text=True, timeout=15,
        )
        files = result.stdout.strip().splitlines()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    counts: Dict[str, int] = {}
    for f in files:
        f = f.strip()
        if f and not f.startswith("."):
            counts[f] = counts.get(f, 0) + 1

    sorted_files = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [{"file": f, "changes": c} for f, c in sorted_files[:limit]]


def scan_complexity(workspace: Path, max_lines: int = 300) -> List[dict]:
    """Find Python files that exceed complexity thresholds."""
    findings: List[dict] = []
    src_dir = workspace / "src"
    if not src_dir.exists():
        return findings

    for py_file in src_dir.rglob("*.py"):
        if py_file.name.startswith("_"):
            continue
        try:
            lines = py_file.read_text(encoding="utf-8").splitlines()
            if len(lines) > max_lines:
                findings.append({
                    "file": str(py_file.relative_to(workspace)),
                    "lines": len(lines),
                    "issue": f"File has {len(lines)} lines (threshold: {max_lines})",
                })

            long_funcs = _find_long_functions(lines, threshold=50)
            for func in long_funcs:
                findings.append({
                    "file": str(py_file.relative_to(workspace)),
                    "lines": func["lines"],
                    "issue": f"Function '{func['name']}' has {func['lines']} lines",
                })
        except OSError:
            continue

    return findings[:15]


def scan_stale_areas(workspace: Path, emap: ExplorationMap) -> List[str]:
    """Find directories that haven't been explored recently."""
    src_dir = workspace / "src"
    if not src_dir.exists():
        return []

    all_dirs: List[str] = []
    for d in src_dir.rglob("*"):
        if d.is_dir() and not d.name.startswith("_") and not d.name.startswith("."):
            rel = str(d.relative_to(workspace))
            all_dirs.append(rel)

    now = time.time()
    stale_threshold = 3600 * 6

    stale: List[tuple[str, float]] = []
    for d in all_dirs:
        status = emap.areas.get(d)
        if not status:
            stale.append((d, float("inf")))
        elif now - status.last_explored_at > stale_threshold:
            stale.append((d, now - status.last_explored_at))

    stale.sort(key=lambda x: x[1], reverse=True)
    return [d for d, _ in stale[:5]]


def build_deep_review_context(workspace: Path, target_dir: str, max_bytes: int = 8000) -> str:
    """Read files in a directory for deep module review."""
    target = workspace / target_dir
    if not target.exists():
        return f"(Directory {target_dir} not found)"

    parts: List[str] = []
    total_bytes = 0

    for py_file in sorted(target.rglob("*.py")):
        if total_bytes >= max_bytes:
            parts.append(f"\n... (truncated, {max_bytes} bytes budget reached)")
            break
        try:
            content = py_file.read_text(encoding="utf-8")
            rel = str(py_file.relative_to(workspace))
            chunk = f"### {rel} ({len(content.splitlines())} lines)\n```python\n{content[:2000]}\n```"
            parts.append(chunk)
            total_bytes += len(chunk)
        except OSError:
            continue

    return "\n\n".join(parts) if parts else "(no Python files found)"


def _find_stale_areas(emap: ExplorationMap) -> List[str]:
    now = time.time()
    threshold = 3600 * 6
    stale = [
        (key, now - s.last_explored_at)
        for key, s in emap.areas.items()
        if now - s.last_explored_at > threshold
    ]
    stale.sort(key=lambda x: x[1], reverse=True)
    return [k for k, _ in stale[:3]]


def _find_high_yield_strategy(emap: ExplorationMap) -> Optional[str]:
    """Find the strategy that historically produces the most tasks."""
    strategy_yield: Dict[str, float] = {}
    for entry in emap.strategy_history[-20:]:
        name = entry.get("strategy", "")
        found = entry.get("tasks_found", 0)
        if name not in strategy_yield:
            strategy_yield[name] = 0
        strategy_yield[name] += found

    if not strategy_yield:
        return None

    best = max(strategy_yield, key=strategy_yield.get)
    return best if strategy_yield[best] > 0 else None


def _find_long_functions(lines: List[str], threshold: int = 50) -> List[dict]:
    """Detect functions longer than threshold lines."""
    functions: List[dict] = []
    current_func: Optional[str] = None
    func_start = 0
    indent_level = 0

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("def ") or stripped.startswith("async def "):
            if current_func and (i - func_start) > threshold:
                functions.append({"name": current_func, "lines": i - func_start, "start": func_start + 1})
            current_func = stripped.split("(")[0].replace("def ", "").replace("async ", "").strip()
            func_start = i
            indent_level = len(line) - len(stripped)

    if current_func and (len(lines) - func_start) > threshold:
        functions.append({"name": current_func, "lines": len(lines) - func_start, "start": func_start + 1})

    return functions

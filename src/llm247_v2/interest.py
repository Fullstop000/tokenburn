"""Interest profile and Issue discovery — the agent's curiosity engine.

Interest sources (where curiosity comes from):
    1. Directive focus_areas — human-directed, highest priority
    2. Experience patterns — areas where the agent has been productive
    3. Exploration yield — strategies/areas that historically produce high-value tasks
    4. Codebase structure — tech stack, dependency landscape, architecture patterns

Issue sources (where concrete problems come from):
    1. GitHub Issues — real user-reported problems via `gh issue list`
    2. Dependency audit — `pip audit` for known vulnerabilities
    3. Web search (LLM-powered) — security advisories, best practices, deprecations
    4. Internal discovery — existing strategies (TODO, test gap, complexity, etc.)

Pipeline: Issues are scored against the Interest profile to produce prioritized Tasks.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from llm247_v2.models import Directive, Task, TaskSource, TaskStatus
from llm247_v2.prompts import render as render_prompt

if TYPE_CHECKING:
    from llm247_v2.experience import ExperienceStore
    from llm247_v2.exploration import ExplorationMap
    from llm247_v2.llm_client import LLMClient

logger = logging.getLogger("llm247_v2.interest")


# ─── Interest Profile ──────────────────────────────

@dataclass
class Interest:
    """One area the agent is interested in, with a strength score."""
    topic: str
    strength: float = 0.5
    source: str = "auto"
    hits: int = 0

    def decay(self, factor: float = 0.95) -> None:
        self.strength = max(0.1, self.strength * factor)

    def boost(self, amount: float = 0.1) -> None:
        self.strength = min(1.0, self.strength + amount)


@dataclass
class InterestProfile:
    """The agent's evolving interest landscape."""
    interests: Dict[str, Interest] = field(default_factory=dict)
    version: int = 0

    def top_interests(self, limit: int = 10) -> List[Interest]:
        return sorted(self.interests.values(), key=lambda i: i.strength, reverse=True)[:limit]

    def score_relevance(self, text: str) -> float:
        """Score how relevant a piece of text is to the agent's interests."""
        if not self.interests:
            return 0.5
        text_lower = text.lower()
        total = 0.0
        matches = 0
        for interest in self.interests.values():
            if interest.topic.lower() in text_lower:
                total += interest.strength
                matches += 1
        return min(1.0, total / max(matches, 1)) if matches else 0.3

    def to_prompt_section(self) -> str:
        """Render interests as context for LLM prompts."""
        top = self.top_interests(8)
        if not top:
            return ""
        lines = ["## Agent Interests (what the agent cares about most)"]
        for i in top:
            lines.append(f"- {i.topic} (strength={i.strength:.2f}, source={i.source})")
        return "\n".join(lines)


def load_interest_profile(path: Path) -> InterestProfile:
    if not path.exists():
        return InterestProfile()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        interests = {}
        for key, val in data.get("interests", {}).items():
            interests[key] = Interest(
                topic=key,
                strength=float(val.get("strength", 0.5)),
                source=str(val.get("source", "auto")),
                hits=int(val.get("hits", 0)),
            )
        return InterestProfile(
            interests=interests,
            version=int(data.get("version", 0)),
        )
    except (json.JSONDecodeError, OSError, ValueError):
        return InterestProfile()


def save_interest_profile(path: Path, profile: InterestProfile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "interests": {
            key: {"strength": i.strength, "source": i.source, "hits": i.hits}
            for key, i in profile.interests.items()
        },
        "version": profile.version + 1,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def build_interest_profile(
    directive: Directive,
    exp_store: Optional["ExperienceStore"] = None,
    emap: Optional["ExplorationMap"] = None,
) -> InterestProfile:
    """Derive the agent's interest profile from all available signals."""
    profile = InterestProfile()

    for area in directive.focus_areas:
        profile.interests[area] = Interest(topic=area, strength=1.0, source="directive")

    if exp_store:
        try:
            stats = exp_store.stats()
            for category, count in stats.get("categories", {}).items():
                if count >= 3:
                    key = f"experience:{category}"
                    profile.interests[key] = Interest(
                        topic=category,
                        strength=min(1.0, 0.3 + count * 0.05),
                        source="experience",
                        hits=count,
                    )

            recent = exp_store.get_recent(limit=30)
            tag_counts: Dict[str, int] = {}
            for exp in recent:
                for tag in exp.tags.split(","):
                    tag = tag.strip().lower()
                    if tag and len(tag) > 2:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
            for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                if count >= 2 and tag not in profile.interests:
                    profile.interests[tag] = Interest(
                        topic=tag,
                        strength=min(0.9, 0.2 + count * 0.1),
                        source="experience_tags",
                        hits=count,
                    )
        except Exception:
            logger.debug("Failed to derive interests from experience store", exc_info=True)

    if emap:
        for entry in emap.strategy_history[-20:]:
            if entry.get("tasks_found", 0) > 0:
                for area in entry.get("areas", []):
                    if area not in profile.interests:
                        profile.interests[area] = Interest(
                            topic=area,
                            strength=0.4,
                            source="exploration_yield",
                        )
                    else:
                        profile.interests[area].boost(0.05)

    return profile


# ─── Issue Discovery: GitHub Issues ─────────────────

def discover_github_issues(
    workspace: Path,
    existing_titles: set[str],
    limit: int = 10,
) -> List[Task]:
    """Pull open issues from the repository's GitHub issue tracker."""
    try:
        result = subprocess.run(
            [
                "gh", "issue", "list",
                "--state=open",
                "--limit", str(limit),
                "--json", "number,title,body,labels",
            ],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.debug("gh issue list failed: %s", result.stderr[:200])
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    tasks: List[Task] = []
    for issue in issues:
        number = issue.get("number", 0)
        title = str(issue.get("title", "")).strip()
        if not title:
            continue

        task_title = f"GitHub #{number}: {title}"
        if task_title in existing_titles:
            continue

        body = str(issue.get("body", ""))[:1000]
        labels = [lbl.get("name", "") for lbl in issue.get("labels", []) if isinstance(lbl, dict)]
        label_str = ", ".join(labels) if labels else "none"

        priority = 2
        if any(l in ("bug", "critical", "urgent") for l in labels):
            priority = 1
        elif any(l in ("enhancement", "feature") for l in labels):
            priority = 3

        task_id = _make_id("gh_issue", str(number), title)
        tasks.append(Task(
            id=task_id,
            title=task_title,
            description=f"GitHub Issue #{number}\nLabels: {label_str}\n\n{body}",
            source=TaskSource.GITHUB_ISSUE.value,
            status=TaskStatus.DISCOVERED.value,
            priority=priority,
        ))

    return tasks


# ─── Issue Discovery: Dependency Audit ───────────────

def discover_dep_vulnerabilities(
    workspace: Path,
    existing_titles: set[str],
) -> List[Task]:
    """Run pip audit to find known vulnerabilities in dependencies."""
    try:
        result = subprocess.run(
            ["pip", "audit", "--format=json", "--desc"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    vulnerabilities = data.get("vulnerabilities", [])
    tasks: List[Task] = []

    for vuln in vulnerabilities[:5]:
        pkg = str(vuln.get("name", "unknown"))
        version = str(vuln.get("version", "?"))
        vuln_id = str(vuln.get("id", ""))
        desc = str(vuln.get("description", ""))[:500]
        fix_versions = vuln.get("fix_versions", [])

        title = f"Security: upgrade {pkg} ({vuln_id})"
        if title in existing_titles:
            continue

        fix_hint = f"Fix available in: {', '.join(fix_versions)}" if fix_versions else "No fix version known"
        task_id = _make_id("dep_audit", pkg, vuln_id)
        tasks.append(Task(
            id=task_id,
            title=title,
            description=f"Package: {pkg}=={version}\nVulnerability: {vuln_id}\n{fix_hint}\n\n{desc}",
            source=TaskSource.DEP_AUDIT.value,
            status=TaskStatus.DISCOVERED.value,
            priority=1,
        ))

    return tasks


# ─── Issue Discovery: Web Search (LLM-powered) ──────

def discover_web_search(
    workspace: Path,
    directive: Directive,
    llm: "LLMClient",
    interest_profile: InterestProfile,
    existing_titles: set[str],
) -> List[Task]:
    """Use LLM knowledge + dependency context to find issues via web-style analysis.

    The LLM acts as a knowledgeable engineer who has read recent security
    advisories, deprecation notices, and best practices for the project's stack.
    """
    from llm247_v2.llm_client import extract_json

    deps_context = _read_dependency_context(workspace)
    stack_context = _detect_tech_stack(workspace)
    interest_section = interest_profile.to_prompt_section()

    prompt = render_prompt(
        "discover_web_search",
        deps_context=deps_context,
        stack_context=stack_context,
        interest_section=interest_section,
        focus=", ".join(directive.focus_areas) if directive.focus_areas else "general quality and security",
    )

    try:
        raw = llm.generate(prompt)
    except Exception:
        logger.exception("Web search discovery LLM call failed")
        return []

    parsed = extract_json(raw)
    if not parsed or not isinstance(parsed.get("tasks"), list):
        return []

    tasks: List[Task] = []
    for item in parsed["tasks"][:5]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title or title in existing_titles:
            continue

        source_type = str(item.get("source_type", "web_search"))
        task_source = TaskSource.WEB_SEARCH.value
        if source_type == "security":
            task_source = TaskSource.DEP_AUDIT.value

        tasks.append(Task(
            id=_make_id("web", title),
            title=title,
            description=str(item.get("description", "")),
            source=task_source,
            status=TaskStatus.DISCOVERED.value,
            priority=min(5, max(1, int(item.get("priority", 2)))),
        ))

    return tasks


# ─── Interest-Driven Discovery ──────────────────────

def discover_interest_driven(
    workspace: Path,
    llm: "LLMClient",
    interest_profile: InterestProfile,
    existing_titles: set[str],
) -> List[Task]:
    """Generate tasks driven by the agent's evolved interests."""
    from llm247_v2.llm_client import extract_json

    if not interest_profile.interests:
        return []

    top = interest_profile.top_interests(5)
    interest_text = "\n".join(f"- {i.topic} (strength={i.strength:.2f})" for i in top)

    file_tree = _get_file_tree(workspace)

    prompt = (
        "You are an autonomous engineering agent exploring a codebase.\n"
        "Based on your evolved interests and the project structure, suggest 1-3 tasks\n"
        "that would satisfy your curiosity AND improve the codebase.\n\n"
        f"## Your Current Interests\n{interest_text}\n\n"
        f"## Project Structure\n{file_tree}\n\n"
        "## Output (strict JSON)\n"
        '{"tasks": [\n'
        '  {"title": "concise task title", "description": "what to do and why", "priority": 3}\n'
        "]}\n"
    )

    try:
        raw = llm.generate(prompt)
    except Exception:
        logger.exception("Interest-driven discovery failed")
        return []

    parsed = extract_json(raw)
    if not parsed or not isinstance(parsed.get("tasks"), list):
        return []

    tasks: List[Task] = []
    for item in parsed["tasks"][:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title or title in existing_titles:
            continue
        tasks.append(Task(
            id=_make_id("interest", title),
            title=title,
            description=str(item.get("description", "")),
            source=TaskSource.INTEREST_DRIVEN.value,
            status=TaskStatus.DISCOVERED.value,
            priority=min(5, max(1, int(item.get("priority", 3)))),
        ))

    return tasks


# ─── Helpers ─────────────────────────────────────────

def _make_id(*parts: str) -> str:
    raw = ":".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _read_dependency_context(workspace: Path) -> str:
    """Read requirements.txt or pyproject.toml for dependency info."""
    for name in ("requirements.txt", "requirements-dev.txt", "pyproject.toml", "setup.cfg"):
        dep_file = workspace / name
        if dep_file.exists():
            try:
                content = dep_file.read_text(encoding="utf-8")[:3000]
                return f"### {name}\n```\n{content}\n```"
            except OSError:
                continue
    return "(no dependency file found)"


def _detect_tech_stack(workspace: Path) -> str:
    """Quick heuristic to detect the project's technology stack."""
    indicators: List[str] = []

    if (workspace / "pyproject.toml").exists() or (workspace / "setup.py").exists():
        indicators.append("Python project")
    if (workspace / "package.json").exists():
        indicators.append("Node.js/JavaScript")
    if (workspace / "Cargo.toml").exists():
        indicators.append("Rust")
    if (workspace / "go.mod").exists():
        indicators.append("Go")
    if (workspace / "Dockerfile").exists():
        indicators.append("Docker")
    if (workspace / ".github").exists():
        indicators.append("GitHub Actions CI")

    try:
        result = subprocess.run(
            ["rg", "--files", "--type", "py", "--count-matches", "."],
            cwd=workspace, capture_output=True, text=True, timeout=10,
        )
        py_count = len(result.stdout.strip().splitlines())
        if py_count > 0:
            indicators.append(f"{py_count} Python files")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return "Tech stack: " + ", ".join(indicators) if indicators else "Tech stack: unknown"


def _get_file_tree(workspace: Path, max_lines: int = 50) -> str:
    """Get a compact file tree for context."""
    try:
        result = subprocess.run(
            ["rg", "--files", "--sort", "path"],
            cwd=workspace, capture_output=True, text=True, timeout=10,
        )
        files = result.stdout.strip().splitlines()[:max_lines]
        return "\n".join(files)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "(file tree unavailable)"

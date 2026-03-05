from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger("llm247_v2.constitution")

IMMUTABLE_PATHS = frozenset({
    "constitution.md",
    "safety.py",
})


@dataclass(frozen=True)
class Constitution:
    """Parsed agent constitution — the immutable identity and operating principles."""

    raw_text: str
    mission: str
    principles: List[str]
    quality_standards: str
    safety_hard_limits: List[str]
    safety_soft_limits: List[str]
    self_modification_rules: List[str]
    decision_priorities: List[str]
    exploration_philosophy: str

    def to_system_prompt(self) -> str:
        """Render constitution as system-level context for all LLM calls."""
        principles_text = "\n".join(f"- {p}" for p in self.principles)
        hard_limits = "\n".join(f"- {h}" for h in self.safety_hard_limits)
        decisions = "\n".join(f"{i+1}. {d}" for i, d in enumerate(self.decision_priorities))

        return (
            "# Agent Constitution\n\n"
            f"## Mission\n{self.mission}\n\n"
            f"## Core Principles\n{principles_text}\n\n"
            f"## Hard Safety Limits\n{hard_limits}\n\n"
            f"## Decision Priorities\n{decisions}\n\n"
            f"## Exploration Philosophy\n{self.exploration_philosophy}\n"
        )

    def to_compact_prompt(self) -> str:
        """Shorter version for token-sensitive contexts."""
        principles_text = "; ".join(self.principles[:3])
        hard_limits = "; ".join(self.safety_hard_limits[:4])
        return (
            f"Mission: {self.mission[:200]}\n"
            f"Principles: {principles_text}\n"
            f"Hard limits: {hard_limits}\n"
        )

    def check_action_allowed(self, action_type: str, target_path: str) -> Tuple[bool, str]:
        """Validate an action against constitution safety boundaries."""
        normalized = target_path
        while normalized.startswith("./"):
            normalized = normalized[2:]

        for immutable in IMMUTABLE_PATHS:
            if normalized.endswith(immutable) or f"/{immutable}" in normalized:
                return False, f"Constitution forbids modifying {immutable}"

        if action_type in ("delete_file", "delete_lines"):
            for limit in self.safety_hard_limits:
                if "no delete" in limit.lower() or "never delete" in limit.lower():
                    return False, f"Constitution hard limit forbids deletion: {limit}"

        lower = normalized.lower()
        if lower == ".env" or lower.startswith(".env.") or "credential" in lower or "secret" in lower:
            return False, "Constitution forbids modifying secret/credential files"

        return True, "allowed"


def load_constitution(path: Path) -> Constitution:
    """Load and parse constitution from markdown file."""
    if not path.exists():
        logger.warning("Constitution file not found at %s, using minimal defaults", path)
        return _default_constitution()

    try:
        raw = path.read_text(encoding="utf-8")
        return _parse_constitution(raw)
    except OSError:
        logger.exception("Failed to read constitution file")
        return _default_constitution()


def _parse_constitution(raw: str) -> Constitution:
    sections = _split_sections(raw)

    mission = sections.get("mission", "").strip()
    if not mission:
        mission = "Continuously improve the engineering quality of the codebase"

    principles = _extract_list_items(sections.get("core principles", ""))
    quality = sections.get("quality standards", "")

    hard_limits = _extract_list_items(sections.get("hard limits", ""))
    if not hard_limits:
        hard_limits = _extract_list_items(sections.get("safety boundaries", ""))

    soft_limits = _extract_list_items(sections.get("soft limits", ""))
    self_mod = _extract_numbered_items(sections.get("self-modification protocol", ""))
    decisions = _extract_numbered_items(sections.get("decision framework", ""))
    exploration = sections.get("exploration philosophy", "")

    default_principles = [
        "Value first", "Minimal change", "Understand before acting",
        "Reversibility", "Transparency",
    ]
    default_hard_limits = [
        "Never force push", "Never modify secret/credential files",
        "Never merge PRs directly",
    ]
    default_decisions = [
        "Safety > Features", "Correctness > Speed", "Simplicity > Cleverness",
    ]

    return Constitution(
        raw_text=raw,
        mission=mission,
        principles=principles or default_principles,
        quality_standards=quality,
        safety_hard_limits=hard_limits or default_hard_limits,
        safety_soft_limits=soft_limits,
        self_modification_rules=self_mod,
        decision_priorities=decisions or default_decisions,
        exploration_philosophy=exploration,
    )


def _default_constitution() -> Constitution:
    return Constitution(
        raw_text="",
        mission="Continuously improve the engineering quality of the codebase",
        principles=[
            "Value first", "Minimal change", "Understand before acting",
            "Reversibility", "Transparency",
        ],
        quality_standards="",
        safety_hard_limits=[
            "Never force push", "Never modify secret/credential files",
            "Never merge PRs directly",
        ],
        safety_soft_limits=[],
        self_modification_rules=[
            "Must create an isolated branch", "Must pass all tests",
            "Must not modify the constitution or safety policy",
        ],
        decision_priorities=[
            "Safety > Features", "Correctness > Speed", "Simplicity > Cleverness",
        ],
        exploration_philosophy="30% exploration, 70% exploitation",
    )


def _split_sections(text: str) -> dict[str, str]:
    """Split markdown by ## and ### headings into named sections."""
    sections: dict[str, str] = {}
    current_name = ""
    current_lines: list[str] = []

    for line in text.splitlines():
        heading_match = re.match(r"^#{2,3}\s+(.+)", line)
        if heading_match:
            if current_name:
                sections[current_name] = "\n".join(current_lines).strip()
            current_name = heading_match.group(1).strip().lower()
            current_lines = []
        else:
            current_lines.append(line)

    if current_name:
        sections[current_name] = "\n".join(current_lines).strip()

    return sections


def _extract_list_items(text: str) -> List[str]:
    """Extract bullet or bold items from markdown text."""
    items: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- **") or line.startswith("- "):
            content = re.sub(r"^-\s+(\*\*)?", "", line).rstrip("*").strip()
            if content:
                items.append(content)
    return items


def _extract_numbered_items(text: str) -> List[str]:
    """Extract numbered list items."""
    items: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        match = re.match(r"^\d+\.\s+\*\*(.+?)\*\*", line)
        if match:
            items.append(match.group(1).strip())
        elif re.match(r"^\d+\.\s+", line):
            content = re.sub(r"^\d+\.\s+", "", line).strip()
            if content:
                items.append(content)
    return items

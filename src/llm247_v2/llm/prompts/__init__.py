"""Centralized prompt template management.

All LLM prompts live as ``.txt`` files in this package directory.
Business code calls ``render("template_name", **params)`` instead of
building prompt strings inline.

Template syntax: standard Python ``str.format_map`` with ``{key}`` placeholders.
Literal braces in JSON examples must be doubled: ``{{`` / ``}}``.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("llm247_v2.llm.prompts")

_PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=32)
def _load_raw(name: str) -> str:
    """Load a template file by name (without .txt extension)."""
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def render(name: str, **kwargs: str) -> str:
    """Load template ``name`` and fill placeholders with kwargs.

    Missing keys are replaced with empty string instead of raising KeyError,
    so optional sections (like experience_section) can be omitted.
    """
    template = _load_raw(name)
    safe = _DefaultDict(kwargs)
    return template.format_map(safe)


def list_templates() -> list[str]:
    """Return names of all available templates."""
    return sorted(p.stem for p in _PROMPTS_DIR.glob("*.txt"))


def get_template_source(name: str) -> str:
    """Return raw template text for inspection/debugging."""
    return _load_raw(name)


def reload() -> None:
    """Clear template cache — useful after editing templates at runtime."""
    _load_raw.cache_clear()


class _DefaultDict(dict):
    """dict subclass that returns empty string for missing keys."""

    def __missing__(self, key: str) -> str:
        logger.debug("Prompt template key not provided: %s", key)
        return ""

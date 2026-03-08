from __future__ import annotations

from typing import Optional


_EXECUTION_NEW_PHASES = {
    "planning": "plan",
    "tool_call": "execute",
    "verification": "verify",
    "state": "execute",
}

_EXECUTION_NEW_ACTIONS = {
    "plan_started": "started",
    "plan_created": "created",
    "replan_triggered": "replan_triggered",
    "replan_created": "replan_created",
    "replan_exhausted": "replan_exhausted",
    "plan_blocked": "constitution_blocked",
    "tool_call_started": "step",
    "tool_call_succeeded": "step",
    "tool_call_failed": "step",
    "verification_completed": "completed",
    "execution_completed": "finished",
    "task_completed": "task_completed",
    "task_failed": "task_failed",
    "task_needs_human": "task_needs_human",
}


def decode_activity_event(entry: dict) -> Optional[dict]:
    """Route one raw activity entry through known module decoders."""
    return decode_discovery_event(entry) or decode_execution_event(entry)


def decode_discovery_event(entry: dict) -> Optional[dict]:
    """Normalize one raw activity row into a Discovery event envelope."""
    module = entry.get("module")
    family = entry.get("family")
    event_name = entry.get("event_name")

    if module == "Discovery" and family and event_name:
        return _normalize_entry(entry, module=module, family=family, event_name=event_name)

    return None


def decode_execution_event(entry: dict) -> Optional[dict]:
    """Normalize one raw activity row into an Execution event envelope."""
    module = entry.get("module")
    family = entry.get("family")
    event_name = entry.get("event_name")

    if module == "Execution" and family and event_name:
        return _normalize_execution_entry(entry, family=family, event_name=event_name)
    return None


def _normalize_entry(entry: dict, *, module: str, family: str, event_name: str) -> dict:
    normalized = dict(entry)
    normalized["module"] = module
    normalized["family"] = family
    normalized["event_name"] = event_name
    normalized.setdefault("data", {})
    normalized["phase"] = "value" if family == "valuation" else "discover"
    normalized["action"] = event_name

    return normalized


def _normalize_execution_entry(entry: dict, *, family: str, event_name: str) -> dict:
    normalized = dict(entry)
    normalized["module"] = "Execution"
    normalized["family"] = family
    normalized["event_name"] = event_name
    normalized.setdefault("data", {})
    normalized["phase"] = _EXECUTION_NEW_PHASES.get(family, normalized.get("phase", "execute"))
    normalized["action"] = _EXECUTION_NEW_ACTIONS.get(event_name, event_name)
    return normalized

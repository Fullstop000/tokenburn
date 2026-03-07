from __future__ import annotations

from llm247_v2.core.models import ToolResult
from llm247_v2.execution.tools import LoopState, ToolRegistry

# Sentinel stored in ToolResult.output to signal the loop to stop.
FINISH_SIGNAL = "__finish__"


def _finish(args: dict, state: LoopState) -> ToolResult:
    summary = args.get("summary", "Task complete")
    return ToolResult("finish", args, True, f"{FINISH_SIGNAL}:{summary}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "finish",
        "description": (
            "Signal that the task is complete. Call this when all changes have been made, "
            "tested, committed, and a PR has been created (if applicable)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "One-sentence summary of what was accomplished",
                },
            },
            "required": ["summary"],
        },
    },
}


def register_all(registry: ToolRegistry) -> None:
    registry.register(_SCHEMA, _finish)

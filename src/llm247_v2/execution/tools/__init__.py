from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from llm247_v2.core.models import Directive, ToolCall, ToolResult
from llm247_v2.execution.git_ops import GitWorkflow
from llm247_v2.execution.safety import SafetyPolicy


@dataclass
class LoopState:
    """Mutable context shared across all tool calls within one ReActLoop run."""

    root_workspace: Path
    active_workspace: Path
    safety: SafetyPolicy
    directive: Directive
    git: GitWorkflow
    task_id: str
    worktree_path: Path | None = None
    branch_name: str = ""
    pr_url: str = ""


ToolHandler = Callable[[dict, LoopState], ToolResult]


class ToolRegistry:
    """Maps tool names to handlers and exposes OpenAI-compatible tool schemas."""

    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}
        self._schemas: list[dict] = []

    def register(self, schema: dict, handler: ToolHandler) -> None:
        name = schema["function"]["name"]
        self._handlers[name] = handler
        self._schemas.append(schema)

    def execute(self, tool_call: ToolCall, state: LoopState) -> ToolResult:
        handler = self._handlers.get(tool_call.tool)
        if handler is None:
            return ToolResult(
                tool=tool_call.tool,
                arguments=tool_call.arguments,
                success=False,
                output=f"unknown tool: {tool_call.tool!r}",
            )
        try:
            return handler(tool_call.arguments, state)
        except Exception as exc:
            return ToolResult(
                tool=tool_call.tool,
                arguments=tool_call.arguments,
                success=False,
                output=f"tool error: {exc}",
            )

    def schemas(self) -> list[dict]:
        return list(self._schemas)


def build_registry(state: LoopState) -> ToolRegistry:
    """Build and return a fully populated ToolRegistry for one loop run."""
    from llm247_v2.execution.tools import filesystem, shell, git, control

    registry = ToolRegistry()
    for module in (filesystem, shell, git, control):
        module.register_all(registry)
    return registry

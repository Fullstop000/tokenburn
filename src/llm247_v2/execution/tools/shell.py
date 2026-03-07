from __future__ import annotations

import subprocess

from llm247_v2.core.models import ToolResult
from llm247_v2.execution.tools import LoopState, ToolRegistry


def _run_command(args: dict, state: LoopState) -> ToolResult:
    command = args.get("command", "")
    tokens = command.split()
    if not tokens:
        return ToolResult("run_command", args, False, "empty command")

    allowed, reason = state.safety.check_command(tokens)
    if not allowed:
        return ToolResult("run_command", args, False, f"blocked: {reason}")

    try:
        result = subprocess.run(
            tokens,
            cwd=state.active_workspace,
            capture_output=True,
            text=True,
            timeout=state.directive.max_steps,  # reuse as a reasonable ceiling
        )
        output = result.stdout.strip() or result.stderr.strip() or "(no output)"
        return ToolResult("run_command", args, result.returncode == 0, output[:4000])
    except subprocess.TimeoutExpired:
        return ToolResult("run_command", args, False, "command timed out")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_command",
        "description": "Execute a shell command in the current workspace. Only allowlisted commands are permitted.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run (no pipes or shell operators)"},
            },
            "required": ["command"],
        },
    },
}


def register_all(registry: ToolRegistry) -> None:
    registry.register(_SCHEMA, _run_command)

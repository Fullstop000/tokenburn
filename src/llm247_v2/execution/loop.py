from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict
from pathlib import Path

from llm247_v2.core.constitution import Constitution
from llm247_v2.core.models import Directive, Task, ToolCall, ToolResult
from llm247_v2.execution.tools import LoopState, ToolRegistry, build_registry
from llm247_v2.execution.tools.control import FINISH_SIGNAL
from llm247_v2.llm.client import BudgetExhaustedError, LLMClient
from llm247_v2.llm.prompts import render
from llm247_v2.observability.observer import AgentEvent, Observer

logger = logging.getLogger("llm247_v2.execution.loop")


class ReActLoop:
    """The agent's decision-and-execution loop.

    The LLM calls tools one at a time, observes real results, and decides
    what to do next. The loop owns nothing beyond the conversation; all
    mutable workspace state lives in LoopState (managed by tool handlers).
    """

    def __init__(
        self,
        llm: LLMClient,
        constitution: Constitution,
        observer: Observer,
        shutdown_event: threading.Event,
    ) -> None:
        self.llm = llm
        self.constitution = constitution
        self.obs = observer
        self._shutdown = shutdown_event

    def run(
        self,
        task: Task,
        workspace: Path,
        directive: Directive,
        experience_context: str = "",
        on_state_change=None,
    ) -> tuple[bool, list[ToolResult], str, LoopState]:
        """Run the ReAct loop for one task.

        Returns (success, trace, failure_reason, state) where failure_reason is
        empty on success and contains the specific error on failure.
        """
        from llm247_v2.execution.git_ops import GitWorkflow
        from llm247_v2.execution.safety import SafetyPolicy

        state = LoopState(
            root_workspace=workspace,
            active_workspace=workspace,
            safety=SafetyPolicy(),
            directive=directive,
            git=GitWorkflow(workspace),
            task_id=task.id,
            task_title=task.title,
            on_state_change=on_state_change,
        )
        registry = build_registry(state)

        system_msg = render(
            "react_execute",
            task_title=task.title,
            task_description=task.description,
            task_source=task.source,
            workspace=str(workspace),
            constitution_summary=self.constitution.to_compact_prompt(),
            experience_section=experience_context,
        )
        messages: list[dict] = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"Begin working on the task: {task.title}"},
        ]
        tool_schemas = registry.schemas()
        trace: list[ToolResult] = []

        for step in range(directive.max_steps):
            if self._shutdown.is_set():
                logger.info("ReActLoop interrupted by shutdown at step %d", step)
                return False, trace, "interrupted by shutdown", state

            # ── LLM call ────────────────────────────────────────────────────
            try:
                _text, tool_calls, _usage = self.llm.generate_with_tools(messages, tool_schemas)
            except BudgetExhaustedError:
                raise
            except Exception as exc:
                reason = f"LLM call failed at step {step}: {exc}"
                logger.warning(reason)
                self.obs.emit(AgentEvent(
                    phase="execute", action="llm_error",
                    task_id=task.id, detail=str(exc), success=False,
                ))
                return False, trace, reason, state

            if not tool_calls:
                # LLM returned text instead of a tool call — nudge it
                messages.append({"role": "assistant", "content": _text or ""})
                messages.append({
                    "role": "user",
                    "content": "Please call one of the available tools to continue.",
                })
                continue

            self.obs.llm_tool_selection(
                task_id=task.id,
                model=str(getattr(self.llm, "_model", getattr(self.llm, "model_name", "")) or ""),
                tool_names=[tool_call.tool for tool_call in tool_calls],
                prompt_tokens=_usage.prompt_tokens,
                completion_tokens=_usage.completion_tokens,
                total_tokens=_usage.total_tokens,
            )

            # ── Execute each tool call ───────────────────────────────────────
            # (OpenAI may return multiple tool calls in one turn)
            assistant_turn: dict = {
                "role": "assistant",
                "content": None,
                "tool_calls": [],
            }
            assistant_reasoning = ""
            tool_result_turns: list[dict] = []

            for idx, tool_call in enumerate(tool_calls):
                call_id = f"call_{step}_{idx}"
                if not assistant_reasoning and tool_call.reasoning:
                    assistant_reasoning = tool_call.reasoning

                assistant_turn["tool_calls"].append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call.tool,
                        "arguments": json.dumps(tool_call.arguments),
                    },
                })

                # Constitution check
                path_arg = tool_call.arguments.get("path", tool_call.arguments.get("command", ""))
                allowed, reason = self.constitution.check_action_allowed(tool_call.tool, path_arg)
                if not allowed:
                    result = ToolResult(tool_call.tool, tool_call.arguments, False,
                                        f"constitution blocked: {reason}")
                else:
                    result = registry.execute(tool_call, state)

                trace.append(result)
                self.obs.execute_step(
                    task.id, step, directive.max_steps,
                    tool_call.tool, path_arg,
                    result.success,
                    output=result.output[:100] if not result.success else "",
                )

                tool_result_turns.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": result.output,
                })

                # Check finish signal
                if result.success and result.output.startswith(FINISH_SIGNAL):
                    if assistant_reasoning:
                        assistant_turn["reasoning_content"] = assistant_reasoning
                    messages.append(assistant_turn)
                    messages.extend(tool_result_turns)
                    return True, trace, "", state

            if assistant_reasoning:
                assistant_turn["reasoning_content"] = assistant_reasoning
            messages.append(assistant_turn)
            messages.extend(tool_result_turns)

        reason = f"exhausted max_steps={directive.max_steps} without calling finish()"
        logger.warning("ReActLoop %s for task %s", reason, task.id)
        self.obs.emit(AgentEvent(
            phase="execute", action="loop_exhausted",
            task_id=task.id, detail=reason, success=False,
        ))
        return False, trace, reason, state


def serialize_trace(trace: list[ToolResult]) -> str:
    """Serialize a tool result trace to a JSON string for storage."""
    return json.dumps([asdict(r) for r in trace], ensure_ascii=False)


def format_execution_log(trace: list[ToolResult]) -> str:
    """Render a trace as a human-readable execution log."""
    lines = []
    for i, r in enumerate(trace):
        status = "OK" if r.success else "FAIL"
        lines.append(f"[{i}] {status} {r.tool}")
        if r.output and not r.output.startswith(FINISH_SIGNAL):
            for line in r.output.splitlines()[:5]:
                lines.append(f"    {line}")
    return "\n".join(lines)

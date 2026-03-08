import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from llm247_v2.core.constitution import load_constitution
from llm247_v2.core.models import Directive, Task, ToolCall, ToolResult
from llm247_v2.execution.loop import ReActLoop
from llm247_v2.llm.client import UsageInfo
from llm247_v2.observability.observer import MemoryHandler, Observer


class _RegistryStub:
    def schemas(self):
        return [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}]

    def execute(self, tool_call, _state):
        if tool_call.tool == "read_file":
            return ToolResult(tool_call.tool, tool_call.arguments, True, "file contents")
        if tool_call.tool == "finish":
            return ToolResult(tool_call.tool, tool_call.arguments, True, "__finish__:done")
        raise AssertionError(f"unexpected tool: {tool_call.tool}")


class _LLMStub:
    def __init__(self):
        self.calls = 0
        self.second_call_messages = None

    def generate_with_tools(self, messages, _tools):
        self.calls += 1
        if self.calls == 1:
            return None, [ToolCall(tool="read_file", arguments={"path": "README.md"}, reasoning="Inspect the repository first.")], UsageInfo()
        if self.calls == 2:
            self.second_call_messages = copy.deepcopy(messages)
            return None, [ToolCall(tool="finish", arguments={"summary": "done"}, reasoning="Enough context gathered.")], UsageInfo()
        raise AssertionError("unexpected extra llm call")


class TestReActLoopReasoningReplay(unittest.TestCase):
    def test_replays_reasoning_content_with_tool_call_turn(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            workspace = Path(tmp.name)
            shutdown_event = MagicMock()
            shutdown_event.is_set.return_value = False
            observer = Observer(handlers=[MemoryHandler()])
            constitution = load_constitution(workspace / "constitution.md")
            llm = _LLMStub()
            loop = ReActLoop(llm=llm, constitution=constitution, observer=observer, shutdown_event=shutdown_event)
            task = Task(id="t1", title="Test task", description="desc", source="manual")
            directive = Directive(max_steps=3)

            with patch("llm247_v2.execution.loop.build_registry", return_value=_RegistryStub()):
                success, trace, reason = loop.run(task, workspace, directive)

            self.assertTrue(success)
            self.assertEqual(reason, "")
            self.assertEqual(len(trace), 2)
            self.assertIsNotNone(llm.second_call_messages)
            assistant_turn = llm.second_call_messages[-2]
            self.assertEqual(assistant_turn["role"], "assistant")
            self.assertEqual(assistant_turn["reasoning_content"], "Inspect the repository first.")
            self.assertEqual(assistant_turn["tool_calls"][0]["function"]["name"], "read_file")
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

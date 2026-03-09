import json
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path

from llm247_v2.core.models import ModelBindingPoint, ModelType, RegisteredModel
from llm247_v2.llm.client import (
    ArkLLMClient,
    LLMAuditLogger,
    RoutedLLMClient,
    TokenTracker,
    UsageInfo,
    extract_json,
    probe_registered_model_connection,
)


class TestUsageInfo(unittest.TestCase):
    def test_frozen(self):
        u = UsageInfo(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        with self.assertRaises(AttributeError):
            u.total_tokens = 50

    def test_defaults(self):
        u = UsageInfo()
        self.assertEqual(u.prompt_tokens, 0)
        self.assertEqual(u.total_tokens, 0)


class TestTokenTracker(unittest.TestCase):
    def test_record_and_total(self):
        t = TokenTracker()
        t.record(UsageInfo(10, 20, 30))
        t.record(UsageInfo(5, 10, 15))
        self.assertEqual(t.total, 45)
        self.assertEqual(t.call_count, 2)

    def test_snapshot(self):
        t = TokenTracker()
        t.record(UsageInfo(10, 20, 30))
        snap = t.snapshot()
        self.assertEqual(snap["prompt_tokens"], 10)
        self.assertEqual(snap["completion_tokens"], 20)
        self.assertEqual(snap["total_tokens"], 30)
        self.assertEqual(snap["call_count"], 1)

    def test_reset(self):
        t = TokenTracker()
        t.record(UsageInfo(10, 20, 30))
        snap = t.reset()
        self.assertEqual(snap["total_tokens"], 30)
        self.assertEqual(t.total, 0)
        self.assertEqual(t.call_count, 0)

    def test_empty(self):
        t = TokenTracker()
        self.assertEqual(t.total, 0)
        self.assertEqual(t.call_count, 0)


class TestExtractJson(unittest.TestCase):
    def test_valid(self):
        result = extract_json('here is {"key": "value"} done')
        self.assertEqual(result, {"key": "value"})

    def test_no_json(self):
        self.assertIsNone(extract_json("no json here"))

    def test_invalid_json(self):
        self.assertIsNone(extract_json("{invalid}"))


class TestLLMAuditLogger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "llm_audit.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_jsonl(self):
        logger = LLMAuditLogger(self.path)
        usage = UsageInfo(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        logger.record("Hello LLM", "Hello Human", usage, duration_ms=420, model="test-model")
        logger.close()

        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)

        entry = json.loads(lines[0])
        self.assertEqual(entry["seq"], 1)
        self.assertEqual(entry["model"], "test-model")
        self.assertEqual(entry["prompt_full"], "Hello LLM")
        self.assertEqual(entry["response_full"], "Hello Human")
        self.assertEqual(entry["prompt_tokens"], 100)
        self.assertEqual(entry["completion_tokens"], 50)
        self.assertEqual(entry["total_tokens"], 150)
        self.assertEqual(entry["duration_ms"], 420)
        self.assertIn("ts", entry)

    def test_increments_seq(self):
        logger = LLMAuditLogger(self.path)
        usage = UsageInfo()
        logger.record("p1", "r1", usage, 100)
        logger.record("p2", "r2", usage, 200)
        logger.record("p3", "r3", usage, 300)
        logger.close()

        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(json.loads(lines[0])["seq"], 1)
        self.assertEqual(json.loads(lines[1])["seq"], 2)
        self.assertEqual(json.loads(lines[2])["seq"], 3)

    def test_records_error(self):
        logger = LLMAuditLogger(self.path)
        logger.record("bad prompt", "", UsageInfo(), 50, error="Connection timeout")
        logger.close()

        entry = json.loads(self.path.read_text(encoding="utf-8").strip())
        self.assertEqual(entry["error"], "Connection timeout")
        self.assertEqual(entry["response_full"], "")

    def test_preview_truncation(self):
        logger = LLMAuditLogger(self.path)
        long_prompt = "x" * 2000
        long_response = "y" * 2000
        logger.record(long_prompt, long_response, UsageInfo(), 100)
        logger.close()

        entry = json.loads(self.path.read_text(encoding="utf-8").strip())
        self.assertEqual(len(entry["prompt_preview"]), 500)
        self.assertEqual(len(entry["prompt_full"]), 2000)
        self.assertEqual(len(entry["response_preview"]), 500)
        self.assertEqual(len(entry["response_full"]), 2000)
        self.assertEqual(entry["prompt_len"], 2000)
        self.assertEqual(entry["response_len"], 2000)

    def test_creates_parent_directory(self):
        deep_path = Path(self.tmp.name) / "sub" / "dir" / "audit.jsonl"
        logger = LLMAuditLogger(deep_path)
        logger.record("p", "r", UsageInfo(), 10)
        logger.close()
        self.assertTrue(deep_path.exists())


class FakePointLLM:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class TestRoutedLLMClient(unittest.TestCase):
    def test_bound_point_uses_registered_model_client(self):
        default_client = FakePointLLM("default")
        bound_client = FakePointLLM("bound")
        routed = RoutedLLMClient(
            default_client=default_client,
            binding_resolver=lambda point: RegisteredModel(
                id="m1",
                model_type="llm",
                base_url="https://example.com/v1",
                model_name="planner-model",
                api_key="secret-ak",
            ) if point == ModelBindingPoint.EXECUTION.value else None,
            client_factory=lambda model: bound_client,
        )

        result = routed.for_point(ModelBindingPoint.EXECUTION.value).generate("plan this")

        self.assertEqual(result, "bound")
        self.assertEqual(bound_client.prompts, ["plan this"])
        self.assertEqual(default_client.prompts, [])

    def test_unbound_point_falls_back_to_default_client(self):
        default_client = FakePointLLM("default")
        routed = RoutedLLMClient(
            default_client=default_client,
            binding_resolver=lambda point: None,
            client_factory=lambda model: FakePointLLM("unused"),
        )

        result = routed.for_point(ModelBindingPoint.TASK_VALUE.value).generate("score this")

        self.assertEqual(result, "default")
        self.assertEqual(default_client.prompts, ["score this"])

    def test_unbound_point_uses_latest_default_model_after_runtime_switch(self):
        fallback_client = FakePointLLM("fallback")
        selected_model = {"id": "m1", "name": "model-one"}
        created_clients: dict[str, FakePointLLM] = {}

        def default_resolver():
            return RegisteredModel(
                id=selected_model["id"],
                model_type="llm",
                base_url="https://example.com/v1",
                model_name=selected_model["name"],
                api_key="secret-ak",
            )

        def client_factory(model: RegisteredModel):
            client = FakePointLLM(model.model_name)
            created_clients[model.id] = client
            return client

        routed = RoutedLLMClient(
            default_client=fallback_client,
            binding_resolver=lambda point: None,
            client_factory=client_factory,
            default_resolver=default_resolver,
        )

        first_result = routed.for_point(ModelBindingPoint.TASK_VALUE.value).generate("score one")
        selected_model["id"] = "m2"
        selected_model["name"] = "model-two"
        second_result = routed.for_point(ModelBindingPoint.TASK_VALUE.value).generate("score two")

        self.assertEqual(first_result, "model-one")
        self.assertEqual(second_result, "model-two")
        self.assertEqual(created_clients["m1"].prompts, ["score one"])
        self.assertEqual(created_clients["m2"].prompts, ["score two"])
        self.assertEqual(fallback_client.prompts, [])


class TestProbeRegisteredModelConnection(unittest.TestCase):
    @patch("llm247_v2.llm.client.urllib.request.urlopen")
    def test_llm_probe_uses_chat_completion_path(self, mock_urlopen):
        response = mock_urlopen.return_value.__enter__.return_value
        response.status = 200
        model = RegisteredModel(
            id="m1",
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="planner-model",
            api_key="secret-ak",
        )

        ok, message = probe_registered_model_connection(model)

        self.assertTrue(ok)
        self.assertEqual(message, "Connection OK")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.com/v1/chat/completions")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "planner-model")
        self.assertEqual(payload["max_tokens"], 1)

    @patch("llm247_v2.llm.client.urllib.request.urlopen")
    def test_embedding_probe_uses_multimodal_text_input(self, mock_urlopen):
        response = mock_urlopen.return_value.__enter__.return_value
        response.status = 200
        model = RegisteredModel(
            id="m2",
            model_type=ModelType.EMBEDDING.value,
            base_url="",
            api_path="https://example.com/api/v3/embeddings/multimodal",
            model_name="embed-model",
            api_key="secret-ak",
        )

        ok, _message = probe_registered_model_connection(model)

        self.assertTrue(ok)
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.com/api/v3/embeddings/multimodal")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "embed-model")
        self.assertEqual(payload["input"][0]["type"], "text")


class TestArkLLMClientToolCalls(unittest.TestCase):
    @patch("llm247_v2.llm.client.ArkLLMClient._extract_usage", return_value=UsageInfo())
    @patch("openai.OpenAI")
    def test_generate_with_tools_preserves_reasoning_content(self, mock_openai_cls, _mock_extract_usage):
        message = SimpleNamespace(
            content=None,
            tool_calls=[
                SimpleNamespace(
                    function=SimpleNamespace(name="run_command", arguments='{"command":"pwd"}')
                )
            ],
            model_extra={"reasoning_content": "Need to inspect the workspace first."},
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        )
        mock_openai_cls.return_value.chat.completions.create.return_value = response

        client = ArkLLMClient(api_key="secret", base_url="https://example.com/v1", model="test-model")

        _text, tool_calls, _usage = client.generate_with_tools(
            messages=[{"role": "user", "content": "inspect"}],
            tools=[{"type": "function", "function": {"name": "run_command", "parameters": {"type": "object"}}}],
        )

        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].reasoning, "Need to inspect the workspace first.")


if __name__ == "__main__":
    unittest.main()

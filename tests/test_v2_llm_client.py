import json
import tempfile
import unittest
from pathlib import Path

from llm247_v2.llm_client import LLMAuditLogger, TokenTracker, UsageInfo, extract_json


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


if __name__ == "__main__":
    unittest.main()

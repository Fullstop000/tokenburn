import json
import tempfile
import unittest
from pathlib import Path

from llm247_v2.storage.experience import (
    Experience,
    ExperienceStore,
    extract_learnings,
    format_experiences_for_prompt,
    format_whats_learned,
)
from llm247_v2.llm.client import extract_json


class TestExperienceStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "exp.db"
        self.store = ExperienceStore(self.db_path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_add_and_get(self):
        exp = Experience(id="e1", task_id="t1", category="pattern", summary="Always run tests before commit")
        self.store.add(exp)
        got = self.store.get("e1")
        self.assertIsNotNone(got)
        self.assertEqual(got.summary, "Always run tests before commit")

    def test_get_nonexistent(self):
        self.assertIsNone(self.store.get("nope"))

    def test_add_batch(self):
        exps = [
            Experience(id=f"e{i}", task_id="t1", category="insight", summary=f"Learning {i}")
            for i in range(5)
        ]
        added = self.store.add_batch(exps)
        self.assertEqual(added, 5)

    def test_ignore_duplicate_id(self):
        exp = Experience(id="e1", task_id="t1", category="pattern", summary="First")
        self.store.add(exp)
        exp2 = Experience(id="e1", task_id="t1", category="pattern", summary="Second")
        self.store.add(exp2)
        got = self.store.get("e1")
        self.assertEqual(got.summary, "First")

    def test_get_recent(self):
        for i in range(10):
            self.store.add(Experience(id=f"e{i}", task_id="t1", category="insight", summary=f"L{i}"))
        recent = self.store.get_recent(limit=3)
        self.assertEqual(len(recent), 3)

    def test_get_by_category(self):
        self.store.add(Experience(id="e1", task_id="t1", category="pattern", summary="P1"))
        self.store.add(Experience(id="e2", task_id="t1", category="pitfall", summary="F1"))
        self.store.add(Experience(id="e3", task_id="t1", category="pattern", summary="P2"))
        patterns = self.store.get_by_category("pattern")
        self.assertEqual(len(patterns), 2)

    def test_search_by_keyword(self):
        self.store.add(Experience(id="e1", task_id="t1", category="pattern", summary="Use pytest for testing", tags="testing,pytest"))
        self.store.add(Experience(id="e2", task_id="t1", category="insight", summary="Database migration needs care", tags="database,sql"))
        results = self.store.search("pytest testing")
        self.assertTrue(any("pytest" in e.summary for e in results))

    def test_search_empty_query(self):
        self.store.add(Experience(id="e1", task_id="t1", category="pattern", summary="Test"))
        results = self.store.search("")
        self.assertEqual(len(results), 1)

    def test_increment_applied(self):
        self.store.add(Experience(id="e1", task_id="t1", category="pattern", summary="X"))
        self.store.increment_applied("e1")
        self.store.increment_applied("e1")
        got = self.store.get("e1")
        self.assertEqual(got.applied_count, 2)

    def test_count_and_stats(self):
        self.store.add(Experience(id="e1", task_id="t1", category="pattern", summary="P"))
        self.store.add(Experience(id="e2", task_id="t1", category="pitfall", summary="F"))
        self.assertEqual(self.store.count(), 2)
        stats = self.store.stats()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["categories"]["pattern"], 1)

    def test_deduplicate(self):
        self.store.add(Experience(id="e1", task_id="t1", category="pattern", summary="Same", confidence=0.9))
        self.store.add(Experience(id="e2", task_id="t2", category="pattern", summary="Same", confidence=0.5))
        removed = self.store.deduplicate()
        self.assertEqual(removed, 1)
        self.assertEqual(self.store.count(), 1)
        remaining = self.store.get("e1")
        self.assertIsNotNone(remaining)

    def test_remove_low_confidence(self):
        self.store.add(Experience(id="e1", task_id="t1", category="pattern", summary="Good", confidence=0.8))
        self.store.add(Experience(id="e2", task_id="t1", category="insight", summary="Weak", confidence=0.1))
        removed = self.store.remove_low_confidence(threshold=0.2)
        self.assertEqual(removed, 1)
        self.assertEqual(self.store.count(), 1)


class TestExtractLearnings(unittest.TestCase):
    def test_parses_valid_response(self):
        def mock_generate(prompt):
            return json.dumps({
                "learnings": [
                    {"category": "pattern", "summary": "Check file exists first", "detail": "d", "tags": "io", "confidence": 0.8},
                    {"category": "pitfall", "summary": "Don't edit binary files", "detail": "d2", "tags": "safety", "confidence": 0.7},
                ]
            })

        results = extract_learnings(
            task_title="Fix parser",
            task_source="todo_scan",
            task_id="t123",
            execution_log="step 1: ok\nstep 2: ok",
            verification_result="passed",
            error_message="",
            outcome="completed",
            llm_generate=mock_generate,
            extract_json_fn=extract_json,
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].category, "pattern")
        self.assertEqual(results[0].task_id, "t123")
        self.assertEqual(results[0].source_outcome, "completed")

    def test_handles_llm_failure(self):
        def mock_fail(prompt):
            raise RuntimeError("LLM down")

        results = extract_learnings("t", "s", "id", "", "", "", "failed", mock_fail, extract_json)
        self.assertEqual(results, [])

    def test_handles_bad_json(self):
        results = extract_learnings(
            "t", "s", "id", "", "", "", "failed",
            lambda p: "not json",
            extract_json,
        )
        self.assertEqual(results, [])

    def test_confidence_clamped(self):
        def mock_generate(prompt):
            return json.dumps({
                "learnings": [{"category": "x", "summary": "y", "confidence": 5.0}]
            })

        results = extract_learnings("t", "s", "id", "", "", "", "completed", mock_generate, extract_json)
        self.assertLessEqual(results[0].confidence, 1.0)


class TestFormatting(unittest.TestCase):
    def test_format_for_prompt(self):
        exps = [
            Experience(id="e1", task_id="t1", category="pattern", summary="Always test first", detail="Run pytest before commit"),
            Experience(id="e2", task_id="t1", category="pitfall", summary="Don't modify .env"),
        ]
        text = format_experiences_for_prompt(exps)
        self.assertIn("Past Experiences", text)
        self.assertIn("Always test first", text)
        self.assertIn("Don't modify .env", text)

    def test_format_empty(self):
        self.assertEqual(format_experiences_for_prompt([]), "")

    def test_format_whats_learned(self):
        exps = [Experience(id="e1", task_id="t1", category="insight", summary="DB is slow", detail="Use indexes")]
        text = format_whats_learned(exps)
        self.assertIn("[insight]", text)
        self.assertIn("DB is slow", text)


if __name__ == "__main__":
    unittest.main()

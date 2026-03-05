"""Tests for llm247_v2.discovery — Task discovery pipeline."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm247_v2.constitution import _default_constitution
from llm247_v2.discovery import (
    _build_rich_context,
    _extract_tag,
    _make_id,
    _parse_llm_tasks,
    _scan_complexity_tasks,
    _scan_dependency_tasks,
    _scan_test_gaps,
    _scan_todos,
    discover_and_evaluate,
)
from llm247_v2.exploration import ExplorationMap
from llm247_v2.models import Directive


class FakeLLM:
    def __init__(self, response: str = ""):
        self.response = response
        self.calls = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response


class TestMakeId(unittest.TestCase):
    def test_deterministic(self):
        a = _make_id("todo", "file.py", "fix bug")
        b = _make_id("todo", "file.py", "fix bug")
        self.assertEqual(a, b)

    def test_different_inputs(self):
        a = _make_id("todo", "a.py")
        b = _make_id("todo", "b.py")
        self.assertNotEqual(a, b)

    def test_length(self):
        result = _make_id("x", "y", "z")
        self.assertEqual(len(result), 12)


class TestExtractTag(unittest.TestCase):
    def test_todo(self):
        self.assertEqual(_extract_tag("# TODO: fix this"), "TODO")

    def test_fixme(self):
        self.assertEqual(_extract_tag("// FIXME: broken"), "FIXME")

    def test_bug(self):
        self.assertEqual(_extract_tag("# BUG: null pointer"), "BUG")

    def test_no_tag(self):
        self.assertEqual(_extract_tag("normal code"), "TODO")


class TestScanTestGaps(unittest.TestCase):
    def test_finds_missing_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "src" / "pkg").mkdir(parents=True)
            (ws / "tests").mkdir()
            (ws / "src" / "pkg" / "auth.py").write_text("class Auth: pass")
            (ws / "tests" / "test_other.py").write_text("pass")
            tasks = _scan_test_gaps(ws, set())
            titles = [t.title for t in tasks]
            self.assertTrue(any("auth.py" in t for t in titles))

    def test_no_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "src" / "pkg").mkdir(parents=True)
            (ws / "tests").mkdir()
            (ws / "src" / "pkg" / "auth.py").write_text("pass")
            (ws / "tests" / "test_auth.py").write_text("pass")
            tasks = _scan_test_gaps(ws, set())
            self.assertEqual(len(tasks), 0)

    def test_skips_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "src" / "pkg").mkdir(parents=True)
            (ws / "tests").mkdir()
            (ws / "src" / "pkg" / "auth.py").write_text("pass")
            tasks = _scan_test_gaps(ws, {"Add tests for src/pkg/auth.py"})
            self.assertEqual(len(tasks), 0)


class TestScanComplexityTasks(unittest.TestCase):
    def test_finds_long_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "src").mkdir()
            long_content = "\n".join(f"x = {i}" for i in range(400))
            (ws / "src" / "big.py").write_text(long_content)
            tasks = _scan_complexity_tasks(ws, set())
            self.assertTrue(any("big.py" in t.description for t in tasks))


class TestScanDependencyTasks(unittest.TestCase):
    def test_finds_high_coupling(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "src").mkdir()
            imports = "\n".join(f"import mod{i}" for i in range(20))
            (ws / "src" / "coupled.py").write_text(imports + "\npass")
            tasks = _scan_dependency_tasks(ws, set())
            self.assertTrue(any("coupled.py" in t.title for t in tasks))


class TestParseLlmTasks(unittest.TestCase):
    def test_valid_response(self):
        llm = FakeLLM(json.dumps({
            "tasks": [
                {"title": "Fix auth", "description": "Auth is broken", "priority": 2},
                {"title": "Add tests", "description": "Missing tests", "priority": 3},
            ]
        }))
        tasks = _parse_llm_tasks(llm, "prompt", "self_improvement", set())
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].title, "Fix auth")

    def test_bad_response(self):
        llm = FakeLLM("not json")
        tasks = _parse_llm_tasks(llm, "prompt", "self_improvement", set())
        self.assertEqual(len(tasks), 0)

    def test_skips_existing(self):
        llm = FakeLLM(json.dumps({
            "tasks": [{"title": "Fix auth", "description": "broken"}]
        }))
        tasks = _parse_llm_tasks(llm, "prompt", "self_improvement", {"Fix auth"})
        self.assertEqual(len(tasks), 0)

    def test_max_three_tasks(self):
        llm = FakeLLM(json.dumps({
            "tasks": [
                {"title": f"Task {i}", "description": f"desc {i}"}
                for i in range(10)
            ]
        }))
        tasks = _parse_llm_tasks(llm, "prompt", "self_improvement", set())
        self.assertLessEqual(len(tasks), 3)

    def test_llm_exception(self):
        class BrokenLLM:
            def generate(self, prompt):
                raise RuntimeError("fail")
        tasks = _parse_llm_tasks(BrokenLLM(), "prompt", "self_improvement", set())
        self.assertEqual(len(tasks), 0)


class TestBuildRichContext(unittest.TestCase):
    def test_includes_python_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "src").mkdir()
            (ws / "src" / "app.py").write_text("print('hello')")
            context = _build_rich_context(ws)
            self.assertIn("app.py", context)


class TestDiscoverAndEvaluate(unittest.TestCase):
    def test_skips_when_queue_full(self):
        llm = FakeLLM()
        emap = ExplorationMap()
        directive = Directive()
        constitution = _default_constitution()

        with tempfile.TemporaryDirectory() as tmp:
            tasks, log = discover_and_evaluate(
                workspace=Path(tmp),
                directive=directive,
                constitution=constitution,
                llm=llm,
                emap=emap,
                existing_titles=set(),
                queued_count=20,
            )
            self.assertEqual(len(tasks), 0)
            self.assertIn("Skipping", log)


if __name__ == "__main__":
    unittest.main()

import unittest

from llm247_v2.llm.prompts import (
    _DefaultDict,
    get_template_source,
    list_templates,
    reload,
    render,
)


class TestListTemplates(unittest.TestCase):
    def test_returns_all_templates(self):
        names = list_templates()
        self.assertIn("react_execute", names)
        self.assertIn("assess_value", names)
        self.assertIn("extract_learnings", names)
        self.assertIn("discover_stale_area", names)
        self.assertIn("discover_deep_review", names)
        self.assertIn("discover_llm_guided", names)

    def test_plan_task_removed(self):
        names = list_templates()
        self.assertNotIn("plan_task", names)
        self.assertNotIn("replan_task", names)


class TestGetTemplateSource(unittest.TestCase):
    def test_returns_raw_text(self):
        raw = get_template_source("react_execute")
        self.assertIn("{task_title}", raw)
        self.assertIn("{constitution_summary}", raw)

    def test_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            get_template_source("nonexistent_template")


class TestRender(unittest.TestCase):
    def test_react_execute(self):
        result = render(
            "react_execute",
            task_title="Fix bug",
            task_description="Something is broken",
            task_source="todo_scan",
            workspace="/repo",
            constitution_summary="Safety first",
        )
        self.assertIn("Fix bug", result)
        self.assertIn("Something is broken", result)
        self.assertIn("Safety first", result)
        self.assertNotIn("{task_title}", result)

    def test_assess_value(self):
        result = render(
            "assess_value",
            mission="Improve quality",
            principles="Value first; Minimal change",
            focus="testing",
            custom_instructions="Focus on edge cases",
            task_descriptions="- [abc] Fix parser: broken\n- [def] Add test: missing",
        )
        self.assertIn("Improve quality", result)
        self.assertIn("testing", result)
        self.assertIn("[abc]", result)

    def test_extract_learnings(self):
        result = render(
            "extract_learnings",
            outcome_label="succeeded",
            task_title="Fix parser",
            task_source="todo_scan",
            execution_log="step 1 ok",
            verification_section="## Verification Result\nall passed",
            error_section="",
        )
        self.assertIn("succeeded", result)
        self.assertIn("Fix parser", result)
        self.assertIn("all passed", result)

    def test_discover_stale_area(self):
        result = render(
            "discover_stale_area",
            constitution_section="CONST",
            target="src/utils",
            focus="code quality",
            code_context="def helper(): pass",
        )
        self.assertIn("src/utils", result)
        self.assertIn("neglected", result.lower())

    def test_discover_deep_review(self):
        result = render(
            "discover_deep_review",
            constitution_section="CONST",
            target="src/parser",
            code_context="class Parser: ...",
        )
        self.assertIn("Deep Module Review", result)
        self.assertIn("src/parser", result)

    def test_discover_llm_guided(self):
        result = render(
            "discover_llm_guided",
            constitution_section="CONST",
            focus="performance",
            custom_section="## Custom Instructions: Optimize loops",
            repo_context="git status: clean",
        )
        self.assertIn("performance", result)
        self.assertIn("Optimize loops", result)

    def test_missing_key_becomes_empty(self):
        result = render("react_execute", task_title="Only title provided")
        self.assertIn("Only title provided", result)
        self.assertNotIn("{task_title}", result)


class TestDefaultDict(unittest.TestCase):
    def test_present_key(self):
        d = _DefaultDict({"a": "1"})
        self.assertEqual(d["a"], "1")

    def test_missing_key(self):
        d = _DefaultDict({})
        self.assertEqual(d["missing"], "")


class TestReload(unittest.TestCase):
    def test_no_crash(self):
        reload()
        result = render("react_execute", task_title="After reload")
        self.assertIn("After reload", result)


if __name__ == "__main__":
    unittest.main()

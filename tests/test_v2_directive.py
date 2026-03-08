import json
import tempfile
import unittest
from pathlib import Path

from llm247_v2.core.directive import (
    default_directive,
    directive_to_prompt_section,
    load_directive,
    save_directive,
)
from llm247_v2.core.models import Directive, TaskSourceConfig


class TestDirective(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "directive.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_directive(self):
        d = default_directive()
        self.assertFalse(d.paused)
        self.assertIn("code_quality", d.focus_areas)
        self.assertIn("todo_scan", d.task_sources)

    def test_load_missing_file(self):
        d = load_directive(Path("/nonexistent/directive.json"))
        self.assertFalse(d.paused)

    def test_save_and_load(self):
        original = Directive(
            paused=True,
            focus_areas=["perf"],
            forbidden_paths=[".env"],
            max_file_changes_per_task=5,
            custom_instructions="be careful",
            task_sources={"todo_scan": TaskSourceConfig(enabled=False, priority=4)},
            poll_interval_seconds=60,
        )
        save_directive(self.path, original)
        loaded = load_directive(self.path)
        self.assertTrue(loaded.paused)
        self.assertEqual(loaded.focus_areas, ["perf"])
        self.assertEqual(loaded.poll_interval_seconds, 60)
        self.assertFalse(loaded.task_sources["todo_scan"].enabled)

    def test_load_corrupt_file(self):
        self.path.write_text("not json", encoding="utf-8")
        d = load_directive(self.path)
        self.assertFalse(d.paused)

    def test_directive_to_prompt(self):
        d = Directive(
            focus_areas=["testing", "docs"],
            forbidden_paths=[".env"],
            custom_instructions="Focus on unit tests",
            task_sources={"todo_scan": TaskSourceConfig(enabled=True, priority=2)},
        )
        text = directive_to_prompt_section(d)
        self.assertIn("testing", text)
        self.assertIn("Focus on unit tests", text)
        self.assertIn(".env", text)

    def test_load_unknown_fields_dropped(self):
        """Unknown fields should be silently dropped without error."""
        data = {
            "paused": True,
            "focus_areas": ["security"],
            "unknown_field": "should be ignored",
            "nested_unknown": {"key": "value"},
        }
        self.path.write_text(json.dumps(data), encoding="utf-8")
        d = load_directive(self.path)
        self.assertTrue(d.paused)
        self.assertEqual(d.focus_areas, ["security"])
        # Should not have unknown fields
        self.assertFalse(hasattr(d, "unknown_field"))

    def test_load_malformed_integer_returns_default(self):
        """Malformed integer strings should return default directive."""
        data = {
            "paused": False,
            "max_file_changes_per_task": "not_a_number",
        }
        self.path.write_text(json.dumps(data), encoding="utf-8")
        d = load_directive(self.path)
        # Should return default on type error
        self.assertFalse(d.paused)
        self.assertEqual(d.max_file_changes_per_task, 10)  # default value

    def test_load_legacy_max_replan_rounds_mapping(self):
        """Legacy max_replan_rounds field should be mapped to max_steps."""
        data = {
            "paused": False,
            "max_replan_rounds": 100,
        }
        self.path.write_text(json.dumps(data), encoding="utf-8")
        d = load_directive(self.path)
        self.assertEqual(d.max_steps, 100)


if __name__ == "__main__":
    unittest.main()

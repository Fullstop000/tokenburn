import tempfile
import unittest
from pathlib import Path

from llm247_v2.core.constitution import (
    Constitution,
    _default_constitution,
    _parse_constitution,
    load_constitution,
)


SAMPLE_CONSTITUTION = """# Agent Constitution v1

## Mission

I am a 24/7 autonomous engineering agent. Continuously improve the engineering quality of the codebase.

## Core Principles

### 1. Value First
Every action must produce measurable value.

### 2. Minimal Change
Each change should be the smallest necessary.

### 3. Understand Before Acting
Before modifying any code, understand it thoroughly.

## Quality Standards

- All code passes syntax checks

## Safety Boundaries

### Hard Limits
- **Never** execute `rm -rf`
- **Never** force push
- **Never** modify secret/credential files

### Soft Limits
- A single task should not modify more than 10 files

## Self-Modification Protocol

1. **Must create an isolated branch**
2. **Must pass all tests**
3. **Must not modify the constitution file**

## Decision Framework

1. **Safety > Features**
2. **Correctness > Speed**
3. **Simplicity > Cleverness**

## Exploration Philosophy

30% exploration, 70% exploitation. Focus on change hotspots.
"""


class TestConstitution(unittest.TestCase):
    def test_parse_full_constitution(self):
        c = _parse_constitution(SAMPLE_CONSTITUTION)
        self.assertIn("Continuously improve", c.mission)
        self.assertGreater(len(c.principles), 0)
        self.assertGreater(len(c.safety_hard_limits), 0)
        self.assertGreater(len(c.decision_priorities), 0)
        self.assertIn("exploration", c.exploration_philosophy)

    def test_default_constitution(self):
        c = _default_constitution()
        self.assertIn("Value first", c.principles)
        self.assertGreater(len(c.safety_hard_limits), 0)

    def test_load_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(SAMPLE_CONSTITUTION)
            path = Path(f.name)
        c = load_constitution(path)
        self.assertIn("Continuously improve", c.mission)
        path.unlink()

    def test_load_missing_file(self):
        c = load_constitution(Path("/nonexistent/constitution.md"))
        self.assertIn("Value first", c.principles)

    def test_to_system_prompt(self):
        c = _parse_constitution(SAMPLE_CONSTITUTION)
        prompt = c.to_system_prompt()
        self.assertIn("Mission", prompt)
        self.assertIn("Hard Safety Limits", prompt)
        self.assertIn("Decision Priorities", prompt)

    def test_to_compact_prompt(self):
        c = _parse_constitution(SAMPLE_CONSTITUTION)
        compact = c.to_compact_prompt()
        self.assertIn("Mission:", compact)
        self.assertIn("Principles:", compact)

    def test_check_action_constitution_file(self):
        c = _default_constitution()
        allowed, reason = c.check_action_allowed("edit_file", "constitution.md")
        self.assertFalse(allowed)
        self.assertIn("constitution", reason.lower())

    def test_check_action_safety_file(self):
        c = _default_constitution()
        allowed, reason = c.check_action_allowed("edit_file", "src/llm247_v2/safety.py")
        self.assertFalse(allowed)

    def test_check_action_env_file(self):
        c = _default_constitution()
        allowed, reason = c.check_action_allowed("edit_file", ".env")
        self.assertFalse(allowed)

    def test_check_action_normal_file(self):
        c = _default_constitution()
        allowed, reason = c.check_action_allowed("edit_file", "src/utils.py")
        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()

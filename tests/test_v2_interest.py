"""Tests for llm247_v2.interest — Interest profile + Issue discovery."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm247_v2.interest import (
    Interest,
    InterestProfile,
    build_interest_profile,
    discover_dep_vulnerabilities,
    discover_github_issues,
    discover_interest_driven,
    discover_web_search,
    load_interest_profile,
    save_interest_profile,
)
from llm247_v2.models import Directive, TaskSource


class TestInterest(unittest.TestCase):
    def test_decay(self):
        i = Interest(topic="testing", strength=0.8)
        i.decay(factor=0.5)
        self.assertAlmostEqual(i.strength, 0.4)

    def test_decay_floor(self):
        i = Interest(topic="x", strength=0.05)
        i.decay(factor=0.5)
        self.assertEqual(i.strength, 0.1)

    def test_boost(self):
        i = Interest(topic="y", strength=0.5)
        i.boost(0.3)
        self.assertAlmostEqual(i.strength, 0.8)

    def test_boost_ceiling(self):
        i = Interest(topic="z", strength=0.95)
        i.boost(0.2)
        self.assertEqual(i.strength, 1.0)


class TestInterestProfile(unittest.TestCase):
    def test_top_interests(self):
        profile = InterestProfile(interests={
            "a": Interest(topic="a", strength=0.9),
            "b": Interest(topic="b", strength=0.3),
            "c": Interest(topic="c", strength=0.7),
        })
        top = profile.top_interests(2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0].topic, "a")
        self.assertEqual(top[1].topic, "c")

    def test_score_relevance_with_matches(self):
        profile = InterestProfile(interests={
            "testing": Interest(topic="testing", strength=0.8),
            "security": Interest(topic="security", strength=0.6),
        })
        score = profile.score_relevance("Add testing for security module")
        self.assertGreater(score, 0.5)

    def test_score_relevance_no_matches(self):
        profile = InterestProfile(interests={
            "testing": Interest(topic="testing", strength=0.8),
        })
        score = profile.score_relevance("Refactor database layer")
        self.assertAlmostEqual(score, 0.3)

    def test_score_relevance_empty_profile(self):
        profile = InterestProfile()
        score = profile.score_relevance("anything")
        self.assertAlmostEqual(score, 0.5)

    def test_to_prompt_section(self):
        profile = InterestProfile(interests={
            "testing": Interest(topic="testing", strength=0.8, source="directive"),
        })
        section = profile.to_prompt_section()
        self.assertIn("testing", section)
        self.assertIn("0.80", section)

    def test_to_prompt_section_empty(self):
        profile = InterestProfile()
        self.assertEqual(profile.to_prompt_section(), "")


class TestInterestProfilePersistence(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "interest.json"
            profile = InterestProfile(interests={
                "auth": Interest(topic="auth", strength=0.9, source="directive", hits=5),
            })
            save_interest_profile(path, profile)
            loaded = load_interest_profile(path)
            self.assertIn("auth", loaded.interests)
            self.assertAlmostEqual(loaded.interests["auth"].strength, 0.9)
            self.assertEqual(loaded.interests["auth"].hits, 5)

    def test_load_missing_file(self):
        profile = load_interest_profile(Path("/nonexistent/interest.json"))
        self.assertEqual(len(profile.interests), 0)

    def test_load_corrupt_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not json{{{")
            path = Path(f.name)
        profile = load_interest_profile(path)
        self.assertEqual(len(profile.interests), 0)
        path.unlink()


class TestBuildInterestProfile(unittest.TestCase):
    def test_from_directive(self):
        directive = Directive(focus_areas=["auth", "testing"])
        profile = build_interest_profile(directive)
        self.assertIn("auth", profile.interests)
        self.assertIn("testing", profile.interests)
        self.assertEqual(profile.interests["auth"].strength, 1.0)
        self.assertEqual(profile.interests["auth"].source, "directive")


class TestDiscoverGitHubIssues(unittest.TestCase):
    @patch("llm247_v2.interest.subprocess.run")
    def test_parses_issues(self, mock_run):
        mock_run.return_value = type("R", (), {
            "returncode": 0,
            "stdout": json.dumps([
                {"number": 42, "title": "Fix login bug", "body": "Login fails on mobile", "labels": [{"name": "bug"}]},
                {"number": 43, "title": "Add dark mode", "body": "Feature request", "labels": [{"name": "enhancement"}]},
            ]),
            "stderr": "",
        })()
        tasks = discover_github_issues(Path("/tmp"), set())
        self.assertEqual(len(tasks), 2)
        self.assertIn("GitHub #42", tasks[0].title)
        self.assertEqual(tasks[0].source, TaskSource.GITHUB_ISSUE.value)
        self.assertEqual(tasks[0].priority, 1)
        self.assertEqual(tasks[1].priority, 3)

    @patch("llm247_v2.interest.subprocess.run")
    def test_skips_existing(self, mock_run):
        mock_run.return_value = type("R", (), {
            "returncode": 0,
            "stdout": json.dumps([
                {"number": 42, "title": "Fix login bug", "body": "", "labels": []},
            ]),
            "stderr": "",
        })()
        tasks = discover_github_issues(Path("/tmp"), {"GitHub #42: Fix login bug"})
        self.assertEqual(len(tasks), 0)

    @patch("llm247_v2.interest.subprocess.run")
    def test_handles_failure(self, mock_run):
        mock_run.return_value = type("R", (), {
            "returncode": 1, "stdout": "", "stderr": "not a repo",
        })()
        tasks = discover_github_issues(Path("/tmp"), set())
        self.assertEqual(len(tasks), 0)


class TestDiscoverDepVulnerabilities(unittest.TestCase):
    @patch("llm247_v2.interest.subprocess.run")
    def test_parses_vulnerabilities(self, mock_run):
        mock_run.return_value = type("R", (), {
            "returncode": 1,
            "stdout": json.dumps({
                "vulnerabilities": [
                    {"name": "requests", "version": "2.25.0", "id": "CVE-2023-1234",
                     "description": "SSRF vulnerability", "fix_versions": ["2.31.0"]},
                ],
            }),
            "stderr": "",
        })()
        tasks = discover_dep_vulnerabilities(Path("/tmp"), set())
        self.assertEqual(len(tasks), 1)
        self.assertIn("requests", tasks[0].title)
        self.assertEqual(tasks[0].source, TaskSource.DEP_AUDIT.value)
        self.assertEqual(tasks[0].priority, 1)

    @patch("llm247_v2.interest.subprocess.run")
    def test_handles_no_pip_audit(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        tasks = discover_dep_vulnerabilities(Path("/tmp"), set())
        self.assertEqual(len(tasks), 0)


class TestDiscoverWebSearch(unittest.TestCase):
    def test_parses_llm_response(self):
        class FakeLLM:
            def generate(self, prompt):
                return json.dumps({"tasks": [
                    {"title": "Upgrade flask to 3.0", "description": "Flask 2.x deprecated",
                     "priority": 2, "source_type": "deprecation"},
                ]})

        profile = InterestProfile(interests={
            "flask": Interest(topic="flask", strength=0.8),
        })
        with tempfile.TemporaryDirectory() as tmp:
            tasks = discover_web_search(Path(tmp), Directive(), FakeLLM(), profile, set())
            self.assertEqual(len(tasks), 1)
            self.assertIn("flask", tasks[0].title.lower())

    def test_handles_llm_failure(self):
        class BrokenLLM:
            def generate(self, prompt):
                raise RuntimeError("LLM down")

        profile = InterestProfile()
        with tempfile.TemporaryDirectory() as tmp:
            tasks = discover_web_search(Path(tmp), Directive(), BrokenLLM(), profile, set())
            self.assertEqual(len(tasks), 0)


class TestDiscoverInterestDriven(unittest.TestCase):
    def test_generates_tasks(self):
        class FakeLLM:
            def generate(self, prompt):
                return json.dumps({"tasks": [
                    {"title": "Improve error handling in auth", "description": "Better error messages", "priority": 3},
                ]})

        profile = InterestProfile(interests={
            "auth": Interest(topic="auth", strength=0.9),
        })
        with tempfile.TemporaryDirectory() as tmp:
            tasks = discover_interest_driven(Path(tmp), FakeLLM(), profile, set())
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].source, TaskSource.INTEREST_DRIVEN.value)

    def test_empty_profile_returns_nothing(self):
        class FakeLLM:
            def generate(self, prompt):
                return "{}"

        profile = InterestProfile()
        with tempfile.TemporaryDirectory() as tmp:
            tasks = discover_interest_driven(Path(tmp), FakeLLM(), profile, set())
            self.assertEqual(len(tasks), 0)


if __name__ == "__main__":
    unittest.main()

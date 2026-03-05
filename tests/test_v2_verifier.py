"""Tests for llm247_v2.execution.verifier — Post-execution verification checks."""

import tempfile
import unittest
from pathlib import Path

from llm247_v2.execution.verifier import (
    _check_lint,
    _check_no_secrets,
    _check_syntax,
    _check_tests,
    format_verification,
    verify_task,
)


class TestCheckSyntax(unittest.TestCase):
    def test_valid_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "good.py").write_text("x = 1\nprint(x)")
            result = _check_syntax(ws, ["good.py"])
            self.assertTrue(result.passed)

    def test_invalid_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "bad.py").write_text("def f(\n    # broken syntax")
            result = _check_syntax(ws, ["bad.py"])
            self.assertFalse(result.passed)

    def test_no_python_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _check_syntax(Path(tmp), ["readme.md"])
            self.assertTrue(result.passed)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _check_syntax(Path(tmp), ["nonexistent.py"])
            self.assertTrue(result.passed)


class TestCheckNoSecrets(unittest.TestCase):
    def test_clean_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "clean.py").write_text("x = 1\nprint(x)")
            result = _check_no_secrets(ws, ["clean.py"])
            self.assertTrue(result.passed)

    def test_secret_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "leak.py").write_text('api_key = "sk-1234567890"')
            result = _check_no_secrets(ws, ["leak.py"])
            self.assertFalse(result.passed)
            self.assertIn("api_key", result.output)

    def test_env_reference_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "safe.py").write_text('api_key = os.getenv("API_KEY")')
            result = _check_no_secrets(ws, ["safe.py"])
            self.assertTrue(result.passed)

    def test_markdown_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "doc.md").write_text("Set your api_key in .env")
            result = _check_no_secrets(ws, ["doc.md"])
            self.assertTrue(result.passed)


class TestCheckLint(unittest.TestCase):
    def test_no_python_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _check_lint(Path(tmp), ["readme.md"])
            self.assertTrue(result.passed)

    def test_handles_missing_ruff(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "ok.py").write_text("x = 1")
            # If ruff is not installed, should pass gracefully
            result = _check_lint(ws, ["ok.py"])
            self.assertTrue(result.passed)


class TestCheckTests(unittest.TestCase):
    def test_no_test_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _check_tests(Path(tmp))
            self.assertTrue(result.passed)
            self.assertIn("no test directory", result.output)


class TestVerifyTask(unittest.TestCase):
    def test_all_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "clean.py").write_text("x = 1\nprint(x)")
            result = verify_task(ws, ["clean.py"])
            self.assertTrue(result.passed)

    def test_syntax_fail_means_overall_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "bad.py").write_text("def f(\n")
            result = verify_task(ws, ["bad.py"])
            self.assertFalse(result.passed)


class TestFormatVerification(unittest.TestCase):
    def test_format(self):
        from llm247_v2.execution.verifier import CheckResult, VerificationResult
        result = VerificationResult(
            passed=True,
            checks=[CheckResult(name="syntax", passed=True, output="all OK")],
            summary="syntax: PASS",
        )
        text = format_verification(result)
        self.assertIn("PASSED", text)
        self.assertIn("syntax", text)


if __name__ == "__main__":
    unittest.main()

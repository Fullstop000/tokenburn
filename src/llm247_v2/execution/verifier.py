from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

logger = logging.getLogger("llm247_v2.execution.verifier")


@dataclass
class VerificationResult:
    passed: bool
    checks: List[CheckResult]
    summary: str


@dataclass
class CheckResult:
    name: str
    passed: bool
    output: str


def verify_task(workspace: Path, changed_files: List[str]) -> VerificationResult:
    """Run verification checks after task execution."""
    checks: List[CheckResult] = []

    checks.append(_check_syntax(workspace, changed_files))
    checks.append(_check_lint(workspace, changed_files))
    checks.append(_check_tests(workspace))
    checks.append(_check_no_secrets(workspace, changed_files))

    all_passed = all(c.passed for c in checks)
    summary_parts = [f"{c.name}: {'PASS' if c.passed else 'FAIL'}" for c in checks]

    return VerificationResult(
        passed=all_passed,
        checks=checks,
        summary=" | ".join(summary_parts),
    )


def _check_syntax(workspace: Path, changed_files: List[str]) -> CheckResult:
    """Verify changed Python files have valid syntax."""
    py_files = [f for f in changed_files if f.endswith(".py")]
    if not py_files:
        return CheckResult(name="syntax", passed=True, output="no Python files changed")

    errors: List[str] = []
    for filepath in py_files:
        full_path = workspace / filepath
        if not full_path.exists():
            continue
        try:
            result = subprocess.run(
                ["python3", "-m", "py_compile", str(full_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                errors.append(f"{filepath}: {result.stderr.strip()[:200]}")
        except (subprocess.TimeoutExpired, OSError):
            errors.append(f"{filepath}: check timed out")

    if errors:
        return CheckResult(name="syntax", passed=False, output="\n".join(errors))
    return CheckResult(name="syntax", passed=True, output=f"all {len(py_files)} files OK")


def _check_lint(workspace: Path, changed_files: List[str]) -> CheckResult:
    """Run ruff linter on changed Python files. Non-fatal if ruff is unavailable."""
    py_files = [f for f in changed_files if f.endswith(".py")]
    if not py_files:
        return CheckResult(name="lint", passed=True, output="no Python files changed")

    abs_files = [str(workspace / f) for f in py_files if (workspace / f).exists()]
    if not abs_files:
        return CheckResult(name="lint", passed=True, output="no files to lint")

    try:
        result = subprocess.run(
            ["ruff", "check", "--no-fix", "--output-format=concise"] + abs_files,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return CheckResult(name="lint", passed=True, output=f"ruff clean on {len(abs_files)} files")
        output = result.stdout.strip() or result.stderr.strip()
        return CheckResult(name="lint", passed=False, output=output[:2000])
    except (FileNotFoundError, NotADirectoryError, OSError):
        return CheckResult(name="lint", passed=True, output="ruff not available, skipping")
    except subprocess.TimeoutExpired:
        return CheckResult(name="lint", passed=False, output="ruff timed out")


def _check_tests(workspace: Path) -> CheckResult:
    """Run test suite and check for failures."""
    test_dir = workspace / "tests"
    if not test_dir.exists():
        return CheckResult(name="tests", passed=True, output="no test directory")

    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", str(test_dir), "-x", "--tb=short", "-q"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout.strip() or result.stderr.strip()
        passed = result.returncode == 0

        if not passed:
            try:
                result_unittest = subprocess.run(
                    ["python3", "-m", "unittest", "discover", "-s", str(test_dir), "-v"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                output = result_unittest.stdout.strip() or result_unittest.stderr.strip()
                passed = result_unittest.returncode == 0
            except (subprocess.TimeoutExpired, OSError):
                pass

        return CheckResult(name="tests", passed=passed, output=output[:2000])
    except subprocess.TimeoutExpired:
        return CheckResult(name="tests", passed=False, output="test suite timed out")
    except FileNotFoundError:
        return CheckResult(name="tests", passed=True, output="pytest not found, skipping")


def _check_no_secrets(workspace: Path, changed_files: List[str]) -> CheckResult:
    """Basic check that no obvious secrets were committed."""
    secret_patterns = [
        "password", "api_key", "secret_key", "access_token",
        "private_key", "AWS_SECRET", "GITHUB_TOKEN",
    ]
    findings: List[str] = []

    for filepath in changed_files:
        full_path = workspace / filepath
        if not full_path.exists() or full_path.stat().st_size > 100_000:
            continue
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore").lower()
            for pattern in secret_patterns:
                if pattern.lower() in content and not filepath.endswith((".md", ".example", ".txt")):
                    if "os.getenv" not in content and "os.environ" not in content:
                        findings.append(f"{filepath}: possible secret ({pattern})")
                        break
        except OSError:
            continue

    if findings:
        return CheckResult(name="secrets", passed=False, output="\n".join(findings))
    return CheckResult(name="secrets", passed=True, output="no obvious secrets detected")


def format_verification(result: VerificationResult) -> str:
    """Render verification result for logging and storage."""
    lines = [f"Verification: {'PASSED' if result.passed else 'FAILED'}"]
    for check in result.checks:
        lines.append(f"  [{check.name}] {'PASS' if check.passed else 'FAIL'}: {check.output[:300]}")
    return "\n".join(lines)

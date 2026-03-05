from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path
from typing import List, Optional, Tuple

from llm247_v2.core.models import Directive, PlanStep, TaskPlan
from llm247_v2.execution.safety import SafetyPolicy

logger = logging.getLogger("llm247_v2.execution.executor")


class ExecutionResult:
    __slots__ = ("step_index", "action", "target", "success", "output")

    def __init__(self, step_index: int, action: str, target: str, success: bool, output: str) -> None:
        self.step_index = step_index
        self.action = action
        self.target = target
        self.success = success
        self.output = output

    def __repr__(self) -> str:
        return f"[{self.step_index}] {self.action} {self.target} ok={self.success}"


class PlanExecutor:
    """Execute plan steps safely within workspace boundaries."""

    def __init__(
        self,
        workspace: Path,
        safety: SafetyPolicy,
        directive: Directive,
        command_timeout: int = 60,
        max_file_bytes: int = 200_000,
        shutdown_event: Optional[threading.Event] = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.safety = safety
        self.directive = directive
        self.command_timeout = command_timeout
        self.max_file_bytes = max_file_bytes
        self._shutdown = shutdown_event

    def execute_plan(self, plan: TaskPlan) -> Tuple[bool, List[ExecutionResult]]:
        """Execute all plan steps. Return (all_succeeded, results)."""
        results: List[ExecutionResult] = []
        all_ok = True

        for idx, step in enumerate(plan.steps):
            if self._shutdown and self._shutdown.is_set():
                results.append(ExecutionResult(idx, step.action, step.target, False, "shutdown requested"))
                all_ok = False
                logger.info("Execution interrupted by shutdown at step %d/%d", idx, len(plan.steps))
                break

            result = self._execute_step(idx, step)
            results.append(result)
            if not result.success:
                all_ok = False
                logger.warning("Step %d failed: %s %s — %s", idx, step.action, step.target, result.output[:200])
                break

        return all_ok, results

    def _execute_step(self, idx: int, step: PlanStep) -> ExecutionResult:
        try:
            if step.action == "edit_file":
                return self._write_file(idx, step, overwrite=True)
            if step.action == "create_file":
                return self._write_file(idx, step, overwrite=False)
            if step.action == "run_command":
                return self._run_command(idx, step)
            if step.action == "delete_file":
                return self._delete_file(idx, step)
            if step.action == "delete_lines":
                return self._delete_lines(idx, step)
            return ExecutionResult(idx, step.action, step.target, False, f"unsupported action: {step.action}")
        except Exception as exc:
            return ExecutionResult(idx, step.action, step.target, False, f"exception: {exc}")

    def _write_file(self, idx: int, step: PlanStep, overwrite: bool) -> ExecutionResult:
        target = self._resolve_path(step.target)
        if target is None:
            return ExecutionResult(idx, step.action, step.target, False, "path outside workspace")

        if not self.safety.is_path_allowed(step.target, self.directive.forbidden_paths):
            return ExecutionResult(idx, step.action, step.target, False, "path is forbidden")

        if not overwrite and target.exists():
            return ExecutionResult(idx, step.action, step.target, False, "file already exists (use edit_file)")

        content_bytes = step.content.encode("utf-8")
        if len(content_bytes) > self.max_file_bytes:
            return ExecutionResult(idx, step.action, step.target, False, "content exceeds size limit")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(step.content, encoding="utf-8")
        return ExecutionResult(idx, step.action, step.target, True, f"wrote {len(content_bytes)} bytes")

    def _run_command(self, idx: int, step: PlanStep) -> ExecutionResult:
        tokens = step.target.split()
        allowed, reason = self.safety.check_command(tokens)
        if not allowed:
            return ExecutionResult(idx, step.action, step.target, False, f"blocked: {reason}")

        try:
            result = subprocess.run(
                tokens,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.command_timeout,
            )
            output = result.stdout.strip() or result.stderr.strip() or "(empty)"
            return ExecutionResult(idx, step.action, step.target, result.returncode == 0, output[:4000])
        except subprocess.TimeoutExpired:
            return ExecutionResult(idx, step.action, step.target, False, "command timed out")

    def _delete_file(self, idx: int, step: PlanStep) -> ExecutionResult:
        target = self._resolve_path(step.target)
        if target is None:
            return ExecutionResult(idx, step.action, step.target, False, "path outside workspace")

        if not self.safety.is_path_allowed(step.target, self.directive.forbidden_paths):
            return ExecutionResult(idx, step.action, step.target, False, "path is forbidden")

        if not target.exists():
            return ExecutionResult(idx, step.action, step.target, False, "file not found")

        target.unlink()
        return ExecutionResult(idx, step.action, step.target, True, "deleted")

    def _delete_lines(self, idx: int, step: PlanStep) -> ExecutionResult:
        """Remove lines matching content from target file."""
        target = self._resolve_path(step.target)
        if target is None:
            return ExecutionResult(idx, step.action, step.target, False, "path outside workspace")

        if not self.safety.is_path_allowed(step.target, self.directive.forbidden_paths):
            return ExecutionResult(idx, step.action, step.target, False, "path is forbidden")

        if not target.exists():
            return ExecutionResult(idx, step.action, step.target, False, "file not found")

        try:
            original = target.read_text(encoding="utf-8")
        except OSError as exc:
            return ExecutionResult(idx, step.action, step.target, False, f"read error: {exc}")

        lines_to_remove = step.content.strip()
        if not lines_to_remove:
            return ExecutionResult(idx, step.action, step.target, False, "no content specified for removal")

        remove_set = {line.rstrip() for line in lines_to_remove.splitlines()}
        original_lines = original.splitlines(keepends=True)
        kept = [line for line in original_lines if line.rstrip() not in remove_set]

        removed_count = len(original_lines) - len(kept)
        if removed_count == 0:
            return ExecutionResult(idx, step.action, step.target, False, "no matching lines found")

        target.write_text("".join(kept), encoding="utf-8")
        return ExecutionResult(idx, step.action, step.target, True, f"removed {removed_count} lines")

    def _resolve_path(self, relative: str) -> Optional[Path]:
        candidate = (self.workspace / relative).resolve()
        if not str(candidate).startswith(str(self.workspace)):
            return None
        return candidate


def format_execution_log(results: List[ExecutionResult]) -> str:
    """Render execution results as human-readable log."""
    lines: List[str] = []
    for r in results:
        status = "OK" if r.success else "FAIL"
        lines.append(f"[{r.step_index}] {status} {r.action} {r.target}")
        if r.output:
            for line in r.output.splitlines()[:10]:
                lines.append(f"    {line}")
    return "\n".join(lines)

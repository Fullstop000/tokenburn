from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("llm247_v2.git")

SELF_EXEC_PREFIX = "[self-exec]"
_CONVENTIONAL_COMMIT_SUBJECT_RE = re.compile(
    r"^(?P<header>[a-z]+(?:\([^)]+\))?(?:!)?):\s*(?P<description>.*)$",
    flags=re.IGNORECASE,
)


class GitWorkflow:
    """Manage git worktrees, branches, commits, and PRs for autonomous changes.

    Uses `git worktree` to isolate changes from the main workspace where the
    agent itself is running. This prevents self-modification from breaking the
    running process and keeps the primary workspace always on the main branch.
    """

    def __init__(self, workspace: Path, branch_prefix: str = "agent") -> None:
        self.workspace = workspace
        self.branch_prefix = branch_prefix
        self.worktree_root = workspace / ".worktrees"

    def current_branch(self) -> str:
        return self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()

    def is_clean(self) -> bool:
        result = self._run(["git", "status", "--porcelain"])
        return not result.strip()

    def has_remote(self) -> bool:
        result = self._run(["git", "remote"])
        return bool(result.strip())

    def create_worktree(self, task_id: str, title: str) -> Tuple[str, Path]:
        """Create a new git worktree and branch for a task.

        Returns (branch_name, worktree_path). The main workspace stays
        untouched on its current branch.
        """
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", title.lower())[:40].strip("-")
        branch_name = f"{self.branch_prefix}/{task_id[:8]}-{safe_name}"
        worktree_path = self.worktree_root / branch_name.replace("/", "-")

        if worktree_path.exists():
            self.remove_worktree(worktree_path)

        base = self._get_main_branch()
        try:
            self._run(["git", "fetch", "origin", base])
        except GitOperationError:
            pass

        self.worktree_root.mkdir(parents=True, exist_ok=True)

        try:
            base_ref = f"origin/{base}"
            try:
                self._run(["git", "rev-parse", "--verify", base_ref])
            except GitOperationError:
                base_ref = base

            self._run([
                "git", "worktree", "add",
                "-b", branch_name,
                str(worktree_path),
                base_ref,
            ])
        except GitOperationError:
            self._run([
                "git", "worktree", "add",
                "-b", branch_name,
                str(worktree_path),
                "HEAD",
            ])

        logger.info("Created worktree: branch=%s path=%s", branch_name, worktree_path)
        return branch_name, worktree_path

    def stage_and_commit(self, message: str, worktree_path: Path) -> Tuple[bool, str]:
        """Stage all changes and commit within a worktree."""
        self._run_in(worktree_path, ["git", "add", "-A"])

        status = self._run_in(worktree_path, ["git", "status", "--porcelain"])
        if not status.strip():
            return False, "no changes to commit"

        commit_message = self._ensure_self_exec_commit_message(message)
        try:
            output = self._run_in(worktree_path, ["git", "commit", "-m", commit_message])
            logger.info("Committed in worktree: %s", commit_message.split("\n")[0])
            return True, output
        except GitOperationError as exc:
            return False, str(exc)

    def push_branch(self, branch_name: str, worktree_path: Optional[Path] = None) -> Tuple[bool, str]:
        """Push branch to origin."""
        if not self.has_remote():
            return False, "no remote configured"

        cwd = worktree_path or self.workspace
        try:
            output = self._run_in(cwd, ["git", "push", "-u", "origin", branch_name])
            logger.info("Pushed branch: %s", branch_name)
            return True, output
        except GitOperationError as exc:
            return False, str(exc)

    def create_pr(
        self,
        title: str,
        body: str,
        base: Optional[str] = None,
        worktree_path: Optional[Path] = None,
        task_id: str = "",
        task_title: str = "",
    ) -> Tuple[bool, str]:
        """Create a GitHub PR using gh CLI."""
        base_branch = base or self._get_main_branch()
        cwd = worktree_path or self.workspace
        merge_message = self._ensure_self_exec_merge_message(title)
        pr_body = self._ensure_self_exec_pr_body(body, task_id=task_id, task_title=task_title)

        try:
            output = self._run_in(cwd, [
                "gh", "pr", "create",
                "--title", merge_message,
                "--body", pr_body,
                "--base", base_branch,
            ])
            pr_url = ""
            for line in output.strip().splitlines():
                if "github.com" in line:
                    pr_url = line.strip()
                    break
            logger.info("Created PR: %s", pr_url or output[:100])
            return True, pr_url or output
        except GitOperationError as exc:
            return False, str(exc)

    def remove_worktree(self, worktree_path: Path) -> None:
        """Remove a worktree and its directory."""
        try:
            self._run(["git", "worktree", "remove", str(worktree_path), "--force"])
        except GitOperationError:
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)
            try:
                self._run(["git", "worktree", "prune"])
            except GitOperationError:
                pass
        logger.info("Removed worktree: %s", worktree_path)

    def cleanup_branch(self, branch_name: str, worktree_path: Path) -> None:
        """Remove worktree and delete the local branch on failure."""
        self.remove_worktree(worktree_path)
        try:
            self._run(["git", "branch", "-D", branch_name])
            logger.info("Deleted branch: %s", branch_name)
        except GitOperationError:
            pass

    def get_diff_summary(self, worktree_path: Optional[Path] = None) -> str:
        cwd = worktree_path or self.workspace
        try:
            stat = self._run_in(cwd, ["git", "diff", "--stat"])
            return stat[:2000] if stat.strip() else "(no changes)"
        except GitOperationError:
            return "(diff unavailable)"

    def list_worktrees(self) -> list[dict]:
        """List all active worktrees."""
        try:
            output = self._run(["git", "worktree", "list", "--porcelain"])
        except GitOperationError:
            return []

        worktrees: list[dict] = []
        current: dict = {}
        for line in output.splitlines():
            if line.startswith("worktree "):
                if current:
                    worktrees.append(current)
                current = {"path": line[9:]}
            elif line.startswith("HEAD "):
                current["head"] = line[5:]
            elif line.startswith("branch "):
                current["branch"] = line[7:]
        if current:
            worktrees.append(current)
        return worktrees

    def _get_main_branch(self) -> str:
        try:
            result = self._run(["git", "branch", "--list", "main"])
            if result.strip():
                return "main"
        except GitOperationError:
            pass
        return "master"

    def _run(self, command: list[str]) -> str:
        return self._run_in(self.workspace, command)

    def _run_in(self, cwd: Path, command: list[str]) -> str:
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                raise GitOperationError(f"{' '.join(command)} failed: {stderr}")
            return result.stdout
        except subprocess.TimeoutExpired as exc:
            raise GitOperationError(f"{' '.join(command)} timed out") from exc
        except FileNotFoundError as exc:
            raise GitOperationError(f"command not found: {command[0]}") from exc

    def _ensure_self_exec_commit_message(self, message: str) -> str:
        """Prefix commit subject with self-exec marker while keeping conventional format."""
        normalized = (message or "").strip()
        if not normalized:
            return f"chore(agent): {SELF_EXEC_PREFIX} autonomous update"

        first_line, *rest_lines = normalized.splitlines()
        if self._has_self_exec_prefix(first_line):
            return normalized

        match = _CONVENTIONAL_COMMIT_SUBJECT_RE.match(first_line.strip())
        if match:
            header = match.group("header")
            description = match.group("description").strip()
            if self._has_self_exec_prefix(description):
                first_line = f"{header}: {description}"
            elif description:
                first_line = f"{header}: {SELF_EXEC_PREFIX} {description}"
            else:
                first_line = f"{header}: {SELF_EXEC_PREFIX}"
        else:
            first_line = f"{SELF_EXEC_PREFIX} {first_line.strip()}".strip()

        if not rest_lines:
            return first_line
        return "\n".join([first_line, *rest_lines])

    def _ensure_self_exec_merge_message(self, message: str) -> str:
        """Prefix PR title as merge message source for GitHub merge strategies."""
        normalized = (message or "").strip()
        if not normalized:
            return f"{SELF_EXEC_PREFIX} automated merge"
        if self._has_self_exec_prefix(normalized):
            return normalized
        return f"{SELF_EXEC_PREFIX} {normalized}"

    def _ensure_self_exec_pr_body(self, body: str, *, task_id: str = "", task_title: str = "") -> str:
        """Prefix PR body to make autonomous execution explicit in PR content."""
        normalized = (body or "").strip()
        prefix_line = f"{SELF_EXEC_PREFIX} This change was self-executed by Sprout agent."
        metadata_lines: list[str] = []
        if task_id:
            metadata_lines.append(f"Task ID: `{task_id}`")
        if task_title:
            metadata_lines.append(f"Task Title: {task_title}")
        metadata_block = "\n".join(metadata_lines).strip()
        required_prefix = prefix_line if not metadata_block else f"{prefix_line}\n\n{metadata_block}"

        if not normalized:
            return required_prefix

        first_line = normalized.splitlines()[0].strip()
        if self._has_self_exec_prefix(first_line):
            if metadata_block and metadata_block not in normalized:
                remainder = "\n".join(normalized.splitlines()[1:]).strip()
                return f"{required_prefix}\n\n{remainder}" if remainder else required_prefix
            return normalized

        return f"{required_prefix}\n\n{normalized}"

    def _has_self_exec_prefix(self, text: str) -> bool:
        """Check whether text already starts with the self-exec prefix."""
        return text.strip().lower().startswith(SELF_EXEC_PREFIX)


class GitOperationError(Exception):
    """Raised when a git operation fails."""

"""Tests for llm247_v2.execution.git_ops — Git workflow (worktree isolation, branch, commit, push)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from llm247_v2.execution.git_ops import GitWorkflow, GitOperationError


class TestGitWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.git = GitWorkflow(self.workspace, branch_prefix="agent")

    def tearDown(self):
        self.tmp.cleanup()

    def test_worktree_root(self):
        self.assertEqual(self.git.worktree_root, self.workspace / ".worktrees")

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_current_branch(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n", stderr="")
        branch = self.git.current_branch()
        self.assertEqual(branch, "main")

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_is_clean_true(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        self.assertTrue(self.git.is_clean())

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_is_clean_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=" M file.py\n", stderr="")
        self.assertFalse(self.git.is_clean())

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_has_remote_true(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="origin\n", stderr="")
        self.assertTrue(self.git.has_remote())

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_has_remote_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        self.assertFalse(self.git.has_remote())

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_create_worktree_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n", stderr="")
        branch, worktree_path = self.git.create_worktree("abc12345", "Fix bug")
        self.assertIn("agent/", branch)
        self.assertIn("abc12345", branch)
        self.assertIn("fix-bug", branch)

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_create_worktree_sanitizes_special_chars(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n", stderr="")
        branch, _ = self.git.create_worktree("abc12345", "Fix: weird chars!@#$%")
        self.assertNotIn("!", branch)
        self.assertNotIn("@", branch)
        self.assertNotIn("#", branch)

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_create_worktree_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fatal: not a git repo")
        with self.assertRaises(GitOperationError):
            self.git.create_worktree("abc12345", "Fix bug")

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_stage_and_commit_success(self, mock_run):
        captured_commit_cmd = {}

        def side_effect(cmd, **kwargs):
            if "status" in cmd:
                return MagicMock(returncode=0, stdout=" M file.py\n", stderr="")
            if cmd[:2] == ["git", "commit"]:
                captured_commit_cmd["cmd"] = cmd
            return MagicMock(returncode=0, stdout="committed", stderr="")

        mock_run.side_effect = side_effect
        ok, output = self.git.stage_and_commit("fix: test", self.workspace)
        self.assertTrue(ok)
        self.assertIn("-m", captured_commit_cmd["cmd"])
        message = captured_commit_cmd["cmd"][captured_commit_cmd["cmd"].index("-m") + 1]
        self.assertEqual(message, "fix: [self-exec] test")

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_stage_and_commit_nothing(self, mock_run):
        def side_effect(cmd, **kwargs):
            if "status" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        ok, output = self.git.stage_and_commit("fix: test", self.workspace)
        self.assertFalse(ok)
        self.assertIn("no changes", output)

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_push_branch_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="origin\npushed", stderr="")
        ok, output = self.git.push_branch("agent/test-branch", self.workspace)
        self.assertTrue(ok)

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_push_branch_failure(self, mock_run):
        def side_effect(cmd, **kwargs):
            if "remote" in cmd:
                return MagicMock(returncode=0, stdout="origin\n", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="remote rejected")

        mock_run.side_effect = side_effect
        ok, output = self.git.push_branch("agent/test-branch", self.workspace)
        self.assertFalse(ok)

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_push_no_remote(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, output = self.git.push_branch("agent/test-branch")
        self.assertFalse(ok)
        self.assertIn("no remote", output)

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_create_pr_success(self, mock_run):
        captured_gh_cmd = {}

        def side_effect(cmd, **kwargs):
            if cmd[0] == "gh":
                captured_gh_cmd["cmd"] = cmd
                return MagicMock(
                    returncode=0,
                    stdout="https://github.com/org/repo/pull/42\n",
                    stderr="",
                )
            return MagicMock(returncode=0, stdout="main\n", stderr="")

        mock_run.side_effect = side_effect
        ok, output = self.git.create_pr("Fix bug", "## Summary\nFixed it", worktree_path=self.workspace)
        self.assertTrue(ok)
        self.assertIn("github.com", output)
        title = captured_gh_cmd["cmd"][captured_gh_cmd["cmd"].index("--title") + 1]
        body = captured_gh_cmd["cmd"][captured_gh_cmd["cmd"].index("--body") + 1]
        self.assertEqual(title, "[self-exec] Fix bug")
        self.assertTrue(body.startswith("[self-exec] This change was self-executed by Sprout agent."))

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_create_pr_includes_task_backlink_metadata(self, mock_run):
        captured_gh_cmd = {}

        def side_effect(cmd, **kwargs):
            if cmd[0] == "gh":
                captured_gh_cmd["cmd"] = cmd
                return MagicMock(
                    returncode=0,
                    stdout="https://github.com/org/repo/pull/43\n",
                    stderr="",
                )
            return MagicMock(returncode=0, stdout="main\n", stderr="")

        mock_run.side_effect = side_effect
        ok, _output = self.git.create_pr(
            "Fix bug",
            "## Summary\nFixed it",
            worktree_path=self.workspace,
            task_id="task-1234abcd",
            task_title="Fix dashboard polling",
        )
        self.assertTrue(ok)
        body = captured_gh_cmd["cmd"][captured_gh_cmd["cmd"].index("--body") + 1]
        self.assertIn("Task ID: `task-1234abcd`", body)
        self.assertIn("Task Title: Fix dashboard polling", body)

    def test_merge_message_prefix_is_idempotent(self):
        message = self.git._ensure_self_exec_merge_message("[self-exec] Keep prefix")
        self.assertEqual(message, "[self-exec] Keep prefix")

    def test_commit_message_prefix_is_idempotent(self):
        message = self.git._ensure_self_exec_commit_message("fix: [self-exec] do not duplicate")
        self.assertEqual(message, "fix: [self-exec] do not duplicate")

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_create_pr_failure(self, mock_run):
        def side_effect(cmd, **kwargs):
            if cmd[0] == "gh":
                return MagicMock(returncode=1, stdout="", stderr="not authenticated")
            return MagicMock(returncode=0, stdout="main\n", stderr="")

        mock_run.side_effect = side_effect
        ok, output = self.git.create_pr("Fix bug", "body", worktree_path=self.workspace)
        self.assertFalse(ok)

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_get_diff_summary(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=" file.py | 2 +-\n", stderr="")
        diff = self.git.get_diff_summary()
        self.assertIn("file.py", diff)

    @patch("llm247_v2.execution.git_ops.subprocess.run")
    def test_list_worktrees(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="worktree /path/main\nHEAD abc123\nbranch refs/heads/main\n",
            stderr="",
        )
        trees = self.git.list_worktrees()
        self.assertEqual(len(trees), 1)
        self.assertEqual(trees[0]["path"], "/path/main")


class TestGitOperationError(unittest.TestCase):
    def test_str(self):
        err = GitOperationError("branch failed")
        self.assertIn("branch failed", str(err))

    def test_inheritance(self):
        self.assertIsInstance(GitOperationError("x"), Exception)


if __name__ == "__main__":
    unittest.main()

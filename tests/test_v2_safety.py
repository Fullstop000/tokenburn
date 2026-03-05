import unittest

from llm247_v2.safety import SafetyPolicy


class TestSafetyPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = SafetyPolicy()

    def test_allowed_binary(self):
        ok, _ = self.policy.check_command(["ls", "-la"])
        self.assertTrue(ok)

    def test_blocked_binary(self):
        ok, reason = self.policy.check_command(["wget", "http://evil.com"])
        self.assertFalse(ok)
        self.assertIn("not allowed", reason)

    def test_empty_command(self):
        ok, _ = self.policy.check_command([])
        self.assertFalse(ok)

    def test_git_status_allowed(self):
        ok, _ = self.policy.check_command(["git", "status"])
        self.assertTrue(ok)

    def test_git_checkout_allowed(self):
        ok, _ = self.policy.check_command(["git", "checkout", "-b", "feature/x"])
        self.assertTrue(ok)

    def test_git_push_allowed(self):
        ok, _ = self.policy.check_command(["git", "push", "-u", "origin", "feature/x"])
        self.assertTrue(ok)

    def test_git_push_main_blocked(self):
        ok, reason = self.policy.check_command(["git", "push", "origin", "main"])
        self.assertFalse(ok)
        self.assertIn("main", reason)

    def test_git_force_blocked(self):
        ok, reason = self.policy.check_command(["git", "push", "--force", "origin", "feature"])
        self.assertFalse(ok)
        self.assertIn("--force", reason)

    def test_git_no_verify_blocked(self):
        ok, reason = self.policy.check_command(["git", "commit", "--no-verify", "-m", "x"])
        self.assertFalse(ok)

    def test_git_merge_blocked(self):
        ok, reason = self.policy.check_command(["git", "merge", "main"])
        self.assertFalse(ok)

    def test_git_rebase_blocked(self):
        ok, reason = self.policy.check_command(["git", "rebase", "main"])
        self.assertFalse(ok)

    def test_rm_simple_allowed(self):
        ok, _ = self.policy.check_command(["rm", "foo.txt"])
        self.assertTrue(ok)

    def test_rm_recursive_blocked(self):
        ok, reason = self.policy.check_command(["rm", "-rf", "/"])
        self.assertFalse(ok)

    def test_path_allowed(self):
        self.assertTrue(self.policy.is_path_allowed("src/main.py", [".env", ".git"]))

    def test_path_forbidden(self):
        self.assertFalse(self.policy.is_path_allowed(".env", [".env", ".git"]))
        self.assertFalse(self.policy.is_path_allowed(".git/config", []))

    def test_path_git_always_blocked(self):
        self.assertFalse(self.policy.is_path_allowed(".git/HEAD", []))


if __name__ == "__main__":
    unittest.main()

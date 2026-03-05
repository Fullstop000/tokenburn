from __future__ import annotations

from typing import List, Tuple


class SafetyPolicy:
    """Allow-list based command and path safety policy for autonomous execution."""

    ALLOWED_BINARIES = frozenset({
        "ls", "pwd", "cat", "echo", "rg", "find", "head", "tail",
        "wc", "mkdir", "touch", "cp", "mv", "rm",
        "git", "python3", "pytest", "gh", "ruff",
        "pip", "pip3", "curl",
        "grep", "sort", "uniq", "diff", "tr",
    })

    ALLOWED_GIT_SUBCOMMANDS = frozenset({
        "status", "diff", "log", "rev-parse", "branch", "show",
        "checkout", "add", "commit", "push", "stash",
        "worktree", "fetch",
    })

    BLOCKED_GIT_FLAGS = frozenset({"--force", "-f", "--hard", "--no-verify"})

    PROTECTED_BRANCHES = frozenset({"main", "master"})

    def check_command(self, command: List[str]) -> Tuple[bool, str]:
        if not command:
            return False, "empty command"

        program = command[0].split("/")[-1]
        if program not in self.ALLOWED_BINARIES:
            return False, f"binary not allowed: {program}"

        if program == "git":
            return self._check_git(command)
        if program == "rm":
            return self._check_rm(command)

        return True, "allowed"

    def _check_git(self, command: List[str]) -> Tuple[bool, str]:
        if len(command) < 2:
            return False, "git requires subcommand"

        sub = command[1]
        if sub not in self.ALLOWED_GIT_SUBCOMMANDS:
            return False, f"git {sub} is not allowed"

        for flag in command[2:]:
            if flag in self.BLOCKED_GIT_FLAGS:
                return False, f"git flag {flag} is blocked"

        if sub == "push":
            for arg in command[2:]:
                if arg in self.PROTECTED_BRANCHES:
                    return False, f"push to {arg} is blocked"

        if sub == "checkout" and len(command) >= 3:
            target = command[2]
            if target in self.PROTECTED_BRANCHES and "-b" not in command:
                pass  # reading main is OK

        return True, "allowed"

    def _check_rm(self, command: List[str]) -> Tuple[bool, str]:
        if "-r" in command or "-rf" in command or "-fr" in command:
            return False, "recursive rm is blocked"
        return True, "allowed"

    def is_path_allowed(self, path: str, forbidden_paths: List[str]) -> bool:
        normalized = _strip_dot_slash(path)
        for pattern in forbidden_paths:
            clean = _strip_dot_slash(pattern)
            if normalized == clean or normalized.startswith(clean + "/"):
                return False
        parts = normalized.split("/")
        if ".git" in parts:
            return False
        return True


def _strip_dot_slash(path: str) -> str:
    """Remove leading ./ prefix without stripping individual characters."""
    while path.startswith("./"):
        path = path[2:]
    return path

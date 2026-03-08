from __future__ import annotations

from llm247_v2.core.models import ToolResult
from llm247_v2.execution.git_ops import GitOperationError
from llm247_v2.execution.tools import LoopState, ToolRegistry


def _git_create_worktree(args: dict, state: LoopState) -> ToolResult:
    branch_name_hint = args.get("branch_name", "")
    if not branch_name_hint:
        return ToolResult("git_create_worktree", args, False, "branch_name is required")
    if state.worktree_path is not None:
        return ToolResult("git_create_worktree", args, False,
                          f"worktree already active at {state.worktree_path}")
    try:
        branch_name, worktree_path = state.git.create_worktree(state.task_id, branch_name_hint)
        state.worktree_path = worktree_path
        state.branch_name = branch_name
        state.active_workspace = worktree_path
        state.notify_state_change()
        return ToolResult("git_create_worktree", args, True,
                          f"created worktree at {worktree_path} on branch {branch_name}")
    except GitOperationError as exc:
        return ToolResult("git_create_worktree", args, False, str(exc))


def _git_commit(args: dict, state: LoopState) -> ToolResult:
    message = args.get("message", "")
    if not message:
        return ToolResult("git_commit", args, False, "commit message is required")
    if state.worktree_path is None:
        return ToolResult("git_commit", args, False,
                          "no active worktree — call git_create_worktree first")
    try:
        committed, output = state.git.stage_and_commit(message, state.worktree_path)
        if not committed:
            return ToolResult("git_commit", args, False, output or "nothing to commit")
        return ToolResult("git_commit", args, True, output or "committed")
    except GitOperationError as exc:
        return ToolResult("git_commit", args, False, str(exc))


def _git_push(args: dict, state: LoopState) -> ToolResult:
    if state.worktree_path is None or not state.branch_name:
        return ToolResult("git_push", args, False,
                          "no active worktree — call git_create_worktree first")
    try:
        pushed, output = state.git.push_branch(state.branch_name, state.worktree_path)
        if not pushed:
            return ToolResult("git_push", args, False, output or "push failed")
        return ToolResult("git_push", args, True, output or "pushed")
    except GitOperationError as exc:
        return ToolResult("git_push", args, False, str(exc))


def _git_create_pr(args: dict, state: LoopState) -> ToolResult:
    title = args.get("title", "")
    body = args.get("body", "")
    if not title:
        return ToolResult("git_create_pr", args, False, "title is required")
    if state.worktree_path is None:
        return ToolResult("git_create_pr", args, False,
                          "no active worktree — call git_create_worktree first")
    try:
        ok, output = state.git.create_pr(
            title,
            body,
            worktree_path=state.worktree_path,
            task_id=state.task_id,
            task_title=state.task_title,
        )
        if ok:
            state.pr_url = output
            state.notify_state_change()
        return ToolResult("git_create_pr", args, ok, output[:200])
    except GitOperationError as exc:
        return ToolResult("git_create_pr", args, False, str(exc))


_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "git_create_worktree",
            "description": (
                "Create an isolated git worktree on a new branch. "
                "Required before making file edits that should be reviewed as a PR. "
                "After this call, all file tools operate inside the worktree."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "branch_name": {
                        "type": "string",
                        "description": "Descriptive branch name, e.g. 'fix-replan-logic'",
                    },
                },
                "required": ["branch_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Stage all changes in the worktree and create a commit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Conventional commit message, e.g. 'fix(agent): handle empty plan'",
                    },
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_push",
            "description": "Push the current worktree branch to the remote.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_create_pr",
            "description": "Open a pull request for the current worktree branch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "PR title"},
                    "body": {"type": "string", "description": "PR description in markdown"},
                },
                "required": ["title", "body"],
            },
        },
    },
]

_HANDLERS = {
    "git_create_worktree": _git_create_worktree,
    "git_commit": _git_commit,
    "git_push": _git_push,
    "git_create_pr": _git_create_pr,
}


def register_all(registry: ToolRegistry) -> None:
    for schema in _SCHEMAS:
        name = schema["function"]["name"]
        registry.register(schema, _HANDLERS[name])

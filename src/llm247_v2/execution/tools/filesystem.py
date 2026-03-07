from __future__ import annotations

import subprocess
from pathlib import Path

from llm247_v2.core.models import ToolResult
from llm247_v2.execution.tools import LoopState, ToolRegistry

_MAX_READ_BYTES = 8_000
_MAX_FILE_BYTES = 200_000


def _resolve(path_str: str, state: LoopState) -> Path | None:
    """Resolve a relative path inside active_workspace. Returns None if outside."""
    candidate = (state.active_workspace / path_str).resolve()
    if not str(candidate).startswith(str(state.active_workspace.resolve())):
        return None
    return candidate


def _forbidden(path_str: str, state: LoopState) -> bool:
    return not state.safety.is_path_allowed(path_str, state.directive.forbidden_paths)


# ── handlers ──────────────────────────────────────────────────────────────────

def _read_file(args: dict, state: LoopState) -> ToolResult:
    path_str = args.get("path", "")
    target = _resolve(path_str, state)
    if target is None:
        return ToolResult("read_file", args, False, "path outside workspace")
    if not target.exists():
        return ToolResult("read_file", args, False, "file not found")
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        if len(content) > _MAX_READ_BYTES:
            content = content[:_MAX_READ_BYTES] + f"\n... (truncated, {len(content)} chars total)"
        return ToolResult("read_file", args, True, content)
    except OSError as exc:
        return ToolResult("read_file", args, False, f"read error: {exc}")


def _list_directory(args: dict, state: LoopState) -> ToolResult:
    path_str = args.get("path", ".")
    target = _resolve(path_str, state)
    if target is None:
        return ToolResult("list_directory", args, False, "path outside workspace")
    if not target.is_dir():
        return ToolResult("list_directory", args, False, "not a directory")
    try:
        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
        return ToolResult("list_directory", args, True, "\n".join(entries))
    except OSError as exc:
        return ToolResult("list_directory", args, False, f"list error: {exc}")


def _search_files(args: dict, state: LoopState) -> ToolResult:
    pattern = args.get("pattern", "")
    path_str = args.get("path", ".")
    target = _resolve(path_str, state)
    if target is None:
        return ToolResult("search_files", args, False, "path outside workspace")
    try:
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py", "--include=*.md", "--include=*.txt",
             "--include=*.json", "--include=*.yaml", "--include=*.yml",
             pattern, str(target)],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout.strip() or result.stderr.strip() or "(no matches)"
        return ToolResult("search_files", args, True, output[:4000])
    except subprocess.TimeoutExpired:
        return ToolResult("search_files", args, False, "search timed out")


def _write_file(args: dict, state: LoopState) -> ToolResult:
    path_str = args.get("path", "")
    content = args.get("content", "")
    overwrite = args.get("overwrite", False)

    target = _resolve(path_str, state)
    if target is None:
        return ToolResult("write_file", args, False, "path outside workspace")
    if _forbidden(path_str, state):
        return ToolResult("write_file", args, False, "path is forbidden")
    if target.exists() and not overwrite:
        return ToolResult("write_file", args, False,
                          "file already exists — set overwrite=true or use edit_file")
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > _MAX_FILE_BYTES:
        return ToolResult("write_file", args, False, "content exceeds size limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return ToolResult("write_file", args, True, f"wrote {len(content_bytes)} bytes to {path_str}")


def _edit_file(args: dict, state: LoopState) -> ToolResult:
    path_str = args.get("path", "")
    old_string = args.get("old_string", "")
    new_string = args.get("new_string", "")

    if not old_string:
        return ToolResult("edit_file", args, False, "old_string must not be empty")

    target = _resolve(path_str, state)
    if target is None:
        return ToolResult("edit_file", args, False, "path outside workspace")
    if _forbidden(path_str, state):
        return ToolResult("edit_file", args, False, "path is forbidden")
    if not target.exists():
        return ToolResult("edit_file", args, False, "file not found — use write_file to create it")

    try:
        original = target.read_text(encoding="utf-8")
    except OSError as exc:
        return ToolResult("edit_file", args, False, f"read error: {exc}")

    count = original.count(old_string)
    if count == 0:
        return ToolResult("edit_file", args, False, "old_string not found in file")
    if count > 1:
        return ToolResult("edit_file", args, False,
                          f"old_string matches {count} locations — make it more specific")

    updated = original.replace(old_string, new_string, 1)
    target.write_text(updated, encoding="utf-8")
    return ToolResult("edit_file", args, True, f"replaced 1 occurrence in {path_str}")


def _delete_file(args: dict, state: LoopState) -> ToolResult:
    path_str = args.get("path", "")
    target = _resolve(path_str, state)
    if target is None:
        return ToolResult("delete_file", args, False, "path outside workspace")
    if _forbidden(path_str, state):
        return ToolResult("delete_file", args, False, "path is forbidden")
    if not target.exists():
        return ToolResult("delete_file", args, False, "file not found")
    target.unlink()
    return ToolResult("delete_file", args, True, f"deleted {path_str}")


# ── schemas ───────────────────────────────────────────────────────────────────

_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content of a file. Output is truncated at 8000 characters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to workspace root"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories at a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to workspace root (default '.')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a pattern across files using grep. Returns matching lines with filenames and line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "path": {"type": "string", "description": "Directory to search in (default '.')"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write full content to a file. Use for new files or complete rewrites. For targeted edits to existing files, prefer edit_file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to workspace root"},
                    "content": {"type": "string", "description": "Full file content to write"},
                    "overwrite": {"type": "boolean", "description": "Set true to overwrite an existing file (default false)"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact string in an existing file. Fails if old_string is not found or matches more than once — make old_string more specific in that case.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to workspace root"},
                    "old_string": {"type": "string", "description": "Exact string to find and replace"},
                    "new_string": {"type": "string", "description": "Replacement string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to workspace root"},
                },
                "required": ["path"],
            },
        },
    },
]

_HANDLERS = {
    "read_file": _read_file,
    "list_directory": _list_directory,
    "search_files": _search_files,
    "write_file": _write_file,
    "edit_file": _edit_file,
    "delete_file": _delete_file,
}


def register_all(registry: ToolRegistry) -> None:
    for schema in _SCHEMAS:
        name = schema["function"]["name"]
        registry.register(schema, _HANDLERS[name])

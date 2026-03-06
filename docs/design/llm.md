# LLM Module Design

> Module: `src/llm247_v2/llm/`
> Files: `client.py`, `prompts/__init__.py`, `prompts/*.txt`
> Last updated: 2026-03-05

## Purpose

The `llm` package is the agent's only interface to language models. It provides:
- A **protocol** (`LLMClient`) that all LLM backends implement
- A concrete **adapter** (`ArkLLMClient`) for the ByteDance ARK / OpenAI-compatible API
- **Token tracking** (`TokenTracker`) for per-task cost measurement
- **Audit logging** (`LLMAuditLogger`) for full prompt/response traceability
- **Prompt template management** (`prompts/`) for centralized prompt authoring

No other module constructs LLM prompts inline. All prompts are `.txt` files, rendered via `prompts.render()`.

## Client Protocol (`client.py`)

### `LLMClient` (Protocol)

```python
class LLMClient(Protocol):
    def generate(self, prompt: str) -> str: ...
    def generate_tracked(self, prompt: str) -> Tuple[str, UsageInfo]: ...
```

All agent code depends only on this interface. `ArkLLMClient` is the production implementation; tests supply mock implementations.

### `ArkLLMClient`

Wraps the OpenAI SDK pointed at the ARK endpoint (`ARK_BASE_URL`, `ARK_MODEL` env vars).

Every call goes through `generate_tracked()`:
1. Calls `chat.completions.create` with `temperature=0.7`, single user message
2. Extracts `UsageInfo` (prompt/completion/total tokens)
3. Records usage in `TokenTracker`
4. Records full prompt + response in `LLMAuditLogger`
5. Detects budget exhaustion errors → raises `BudgetExhaustedError`

`generate()` is a thin wrapper that calls `generate_tracked()` and discards usage info.

### `BudgetExhaustedError`

Raised when the API returns a quota/rate-limit/budget error (detected by keyword matching in the error message). The agent loop catches this and stops cleanly rather than retrying indefinitely.

### `extract_json(text: str) -> dict | None`

Utility used everywhere to parse LLM output. Finds the first `{...}` in the response and attempts `json.loads`. Returns `None` on failure. This tolerates LLMs that wrap JSON in markdown fences or add surrounding text.

## Token Tracking (`TokenTracker`)

Thread-safe accumulator. The agent takes a `snapshot()` before and after each task to compute per-task token cost, which is stored in `task.token_cost`.

```python
snap_before = tracker.snapshot()
# ... execute task ...
snap_after = tracker.snapshot()
task.token_cost = snap_after["total_tokens"] - snap_before["total_tokens"]
```

`TokenTracker` is attached to `ArkLLMClient` as `.tracker` and retrieved via `_get_tracker(llm)` in `agent.py`.

## Audit Logging (`LLMAuditLogger`)

Every LLM call is written as a JSON line to `.llm247_v2/llm_audit.jsonl`:

```json
{
  "seq": 42,
  "ts": "2026-03-05T10:00:00Z",
  "model": "...",
  "prompt_len": 1234,
  "prompt_preview": "first 500 chars...",
  "prompt_full": "full prompt text",
  "response_len": 456,
  "response_preview": "first 500 chars...",
  "response_full": "full response text",
  "prompt_tokens": 300,
  "completion_tokens": 150,
  "total_tokens": 450,
  "duration_ms": 1200
}
```

Failed calls are also logged with an `"error"` field. The `prompt_full` and `response_full` fields are stripped by the dashboard API by default and only returned on direct `GET /api/llm-audit/<seq>` requests.

## Prompt Template Management (`prompts/`)

### Design

All prompts are `.txt` files in `src/llm247_v2/llm/prompts/`. Business code never builds prompt strings inline — it always calls `prompts.render(name, **kwargs)`.

Template syntax: standard Python `str.format_map` with `{key}` placeholders. Literal braces in JSON examples must be doubled: `{{` / `}}`.

Missing keys render as empty string (via `_DefaultDict`), so optional sections like `{experience_section}` can be omitted by not passing the kwarg.

Templates are loaded once and cached via `@lru_cache`. Call `prompts.reload()` to clear cache after editing templates at runtime.

### Templates

| File | Used by | Purpose |
|------|---------|---------|
| `plan_task.txt` | `planner.py` | Generate execution plan |
| `assess_value.txt` | `value.py` | LLM-based task value scoring |
| `extract_learnings.txt` | `experience.py` | Reflect on task outcome, extract learnings |
| `discover_stale_area.txt` | `pipeline.py` | Find stale/neglected modules |
| `discover_deep_review.txt` | `pipeline.py` | Deep review of a single module |
| `discover_llm_guided.txt` | `pipeline.py` | Open-ended codebase exploration |
| `discover_web_search.txt` | `interest.py` | Security/deprecation analysis via LLM |

### Convention

**Rule:** Every string sent to the LLM as a prompt MUST be a `.txt` template rendered via `prompts.render()`. No inline prompt strings in Python code.

**Why:** Centralized management for auditing, iteration, and version control. Separates prompt engineering from business logic. All prompts are written in English.

## Design Constraints

- **Single model per session** — `ArkLLMClient` is instantiated once in `__main__.py` and injected everywhere. No ad-hoc client creation in business code.
- **No streaming** — the agent uses blocking `generate()` calls. Streaming would complicate audit logging and add no benefit for the current use case.
- **Temperature is fixed at 0.7** — not configurable per-call. If different tasks need different temperatures, this is a future concern.

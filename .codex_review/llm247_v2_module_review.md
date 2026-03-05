# llm247_v2 Implementation Review

Date: 2026-03-05  
Scope: `src/llm247_v2/*` (all Python modules + prompts package helper)  
Reference standard: current `AGENTS.md` (architecture, safety, workflow, and code quality rules)

## Highest-Risk Problems (Ordered)

1. **P0: Tasks can be marked `completed` even when no commit/push/PR succeeds.**  
   Evidence: `src/llm247_v2/agent.py:289`, `src/llm247_v2/agent.py:294`, `src/llm247_v2/agent.py:298`, `src/llm247_v2/agent.py:308`  
   Why this is a problem: Violates “all code changes go through commit → push → PR” and reviewability pillar.

2. **P0: Command safety allows outbound network and package-install primitives (`curl`, `pip`, `pip3`).**  
   Evidence: `src/llm247_v2/safety.py:13`, `src/llm247_v2/safety.py:40`  
   Why this is a problem: Breaks least-privilege safety model and caused failing tests (`test_v2_executor`, `test_v2_safety`).

3. **P0: Dashboard is remotely mutable with no auth and permissive CORS (`*`).**  
   Evidence: `src/llm247_v2/dashboard.py:71`, `src/llm247_v2/dashboard.py:45`, `src/llm247_v2/dashboard.py:150`  
   Why this is a problem: Any reachable client can alter directives or inject/cancel tasks.

4. **P1: Planner fallback returns empty plan, enabling “successful” no-op tasks.**  
   Evidence: `src/llm247_v2/planner.py:126`, `src/llm247_v2/planner.py:131`, `src/llm247_v2/agent.py:246`, `src/llm247_v2/agent.py:308`  
   Why this is a problem: Reliability regression; explicitly failing `tests/test_v2_planner.py:70`.

5. **P1: Path checks are string-prefix based and not canonicalized for forbidden paths.**  
   Evidence: `src/llm247_v2/executor.py:162`, `src/llm247_v2/safety.py:72`  
   Why this is a problem: Directory traversal and sibling-prefix bypass risk (`/repo` vs `/repo2`).

6. **P1: Inline LLM prompt in `experience.py` violates project prompt convention.**  
   Evidence: `src/llm247_v2/experience.py:254`  
   Why this is a problem: Breaks “all prompts in `prompts/*.txt`” project rule and hurts auditability/versioning.

## Module-by-Module Review

### `src/llm247_v2/__init__.py`
- **Assessment:** Neutral.
- **Problems:** None.
- **Notes:** Empty marker module only.

### `src/llm247_v2/__main__.py`
- **Assessment:** Mostly solid startup wiring and graceful shutdown handling.
- **Problems:**
  - **P2:** Runtime assumes environment/tooling alignment but does not validate Python package import path for tests/runtime ergonomics.
    - Evidence: test execution required manual `PYTHONPATH=src`.
- **Notes:** Signal handling and cleanup path are reasonable.

### `src/llm247_v2/agent.py`
- **Assessment:** Good orchestration shape, but core workflow invariants are not enforced.
- **Problems:**
  - **P0:** Marks tasks `completed` regardless of git deliverable success.
    - Evidence: `:289-305`, `:308-319`
  - **P1:** If worktree creation fails, execution continues in main workspace without branch/PR isolation.
    - Evidence: `:223-238`
  - **P1:** Combined with empty fallback plan, zero-change tasks can be “completed”.
    - Evidence: `:201-207`, `:246-249`, `:308-319`
  - **P2:** Duplicate suppression during discovery only uses the latest 200 task titles.
    - Evidence: `:125`

### `src/llm247_v2/constitution.py`
- **Assessment:** Clear parser and default behavior.
- **Problems:**
  - **P2:** Hard-limit enforcement depends on fragile string matching (“no delete” text search).
    - Evidence: `:67-69`
  - **P3:** Parsing is markdown-shape sensitive (`##/###` + specific list styles).
    - Evidence: `:161-206`

### `src/llm247_v2/dashboard.py`
- **Assessment:** Functional control plane, but security and robustness are weak.
- **Problems:**
  - **P0:** No auth for mutating APIs.
    - Evidence: `:45-55`, `:150-169`, `:172-203`
  - **P0:** `Access-Control-Allow-Origin: *` on control API.
    - Evidence: `:71`
  - **P1:** Unescaped task content is inserted into HTML (`innerHTML`), enabling XSS in dashboard context.
    - Evidence: `:381-390`, `:546-574`
  - **P2:** API always returns HTTP 200 with embedded error object; operational ambiguity.
    - Evidence: `:66-74`, `:106-112`, `:172-183`, `:185-203`
  - **P2:** `int(...)` casts on user input can throw and terminate request handling thread.
    - Evidence: `:155-157`, `:163`, `:166`, `:198`
  - **P3:** Single 500+ line mixed server/UI file violates modularity guideline.
    - Evidence: file length and inline HTML/JS/CSS.

### `src/llm247_v2/directive.py`
- **Assessment:** Good defaulting and atomic write pattern.
- **Problems:**
  - **P2:** Silent fallback to defaults on load errors hides config corruption.
    - Evidence: `:51-52`
  - **P2:** Weak schema/type validation for list fields (can accept wrong shapes).
    - Evidence: `:44-49`

### `src/llm247_v2/discovery.py`
- **Assessment:** Strong strategy pipeline concept; several parser/robustness gaps.
- **Problems:**
  - **P1:** LLM priority parsing can throw `ValueError` and abort discovery path.
    - Evidence: `:433`
  - **P2:** `_build_rich_context` ignores command return codes and may record empty/misleading context.
    - Evidence: `:443-468`
  - **P2:** De-dup strategy relies on title strings; brittle under minor wording changes.
    - Evidence: `:212`, `:244`, `:268`, `:291`

### `src/llm247_v2/executor.py`
- **Assessment:** Execution surface is compact but safety boundaries are not robust enough.
- **Problems:**
  - **P1:** Workspace boundary check uses `startswith` string comparison; prefix-collision risk.
    - Evidence: `:162`
  - **P1:** Command tokenizer uses `.split()` instead of shell-safe parsing; quoted args break.
    - Evidence: `:96`
  - **P1:** Behavior depends on weak `SafetyPolicy` allowlist (currently permits `curl`).
    - Evidence: `:97`
  - **P2:** Catch-all exception erases stack/context from execution results.
    - Evidence: `:73-74`

### `src/llm247_v2/experience.py`
- **Assessment:** Useful long-term memory design; implementation partially diverges from project conventions.
- **Problems:**
  - **P1:** Inline LLM prompt string violates “all prompts in `prompts/*.txt`”.
    - Evidence: `:254-263`
  - **P2:** `float(item.get("confidence"))` in learning extraction can raise and abort extraction for malformed items.
    - Evidence: `:370`
  - **P3:** Keyword-cluster merge heuristic is brittle (`sorted(set(words))[:3]`).
    - Evidence: `:244-246`

### `src/llm247_v2/exploration.py`
- **Assessment:** Valuable exploration map concept; shared mutable state bug present.
- **Problems:**
  - **P1:** `select_strategy()` mutates global strategy instance (`target_areas`), causing cross-cycle state bleed.
    - Evidence: `:163`
  - **P3:** Unused parameter (`constitution`) signals incomplete design integration.
    - Evidence: `:151`

### `src/llm247_v2/git_ops.py`
- **Assessment:** Worktree abstraction is useful; several safety/reliability edges.
- **Problems:**
  - **P1:** Uses forced worktree removal by default.
    - Evidence: `:141`
  - **P2:** Main branch detection limited to `main/master`; ignores remote default branch metadata.
    - Evidence: `:190-197`
  - **P2:** Error messages only include stderr, can hide stdout diagnostics.
    - Evidence: `:212-214`

### `src/llm247_v2/llm_client.py`
- **Assessment:** Clean adapter layering and audit hook.
- **Problems:**
  - **P1:** `_is_budget_error` treats generic rate-limit signals as budget exhaustion, potentially stopping loop on transient failures.
    - Evidence: `:195-197`
  - **P2:** Stores full prompt/response in audit log, increasing secret/data exposure blast radius.
    - Evidence: `:113`, `:116`
  - **P3:** Read properties `total` / `call_count` are unlocked.
    - Evidence: `:50-56`

### `src/llm247_v2/models.py`
- **Assessment:** Simple DTOs are easy to use.
- **Problems:**
  - **P2:** Core fields (`source`, `status`) are plain strings in `Task`; invalid states are representable.
    - Evidence: `:33-35`
  - **P3:** Missing explicit model-level validation/invariants.

### `src/llm247_v2/observer.py`
- **Assessment:** Good centralized event architecture.
- **Problems:**
  - **P2:** Handler failures are swallowed; observability pipeline can silently degrade.
    - Evidence: `:272-277`, `:443-455`
  - **P3:** No async queue/backpressure; synchronous handlers can slow agent cycle.
    - Evidence: `:272-277`

### `src/llm247_v2/planner.py`
- **Assessment:** Prompt-driven planner is clear; fallback logic regressed.
- **Problems:**
  - **P1:** Fallback plan intentionally returns zero steps and empty commit message.
    - Evidence: `:126-135`
  - **P2:** Imports private `_default_constitution` from another module.
    - Evidence: `:44-45`
  - **P2:** No action whitelist at parse stage; invalid actions survive until executor failure.
    - Evidence: `:65-74`

### `src/llm247_v2/prompts/__init__.py`
- **Assessment:** Useful centralized prompt loader.
- **Problems:**
  - **P2:** Template inventory drift (`discover_web_search`) not aligned with existing tests/strategy map.
    - Evidence: `list_templates()` + file set; failing test `tests/test_v2_prompts.py:21`.
  - **P3:** No explicit allowlist/versioned prompt registry.

### `src/llm247_v2/safety.py`
- **Assessment:** Safety boundary exists, but policy is too permissive and path validation is weak.
- **Problems:**
  - **P0:** Allows `curl`, `pip`, `pip3` in autonomous command execution.
    - Evidence: `:13`
  - **P1:** `is_path_allowed()` does not canonicalize `..`/symlink paths.
    - Evidence: `:71-79`
  - **P2:** Protected branch push detection only checks raw argument equality.
    - Evidence: `:54-57`

### `src/llm247_v2/store.py`
- **Assessment:** SQLite schema is clear and practical.
- **Problems:**
  - **P2:** Read operations are not lock-protected while sharing one connection across threads.
    - Evidence: `:160`, `:170`, `:175`, `:183`, `:206`, `:240`, `:260`
  - **P2:** Migration errors are silently ignored.
    - Evidence: `:113-114`
  - **P3:** No rowcount checks on `update_task()` (missing task updates are silent).
    - Evidence: `:141-157`

### `src/llm247_v2/value.py`
- **Assessment:** Good two-tier scoring shape; scoring semantics are inconsistent.
- **Problems:**
  - **P1:** `risk` dimension is averaged positively; higher risk increases score.
    - Evidence: `:106`, `:109`
  - **P2:** Heuristic stemming uses chained `rstrip()` character-set semantics, producing unstable matches.
    - Evidence: `:223`

### `src/llm247_v2/verifier.py`
- **Assessment:** Verification stages are present, but gating strictness is weak.
- **Problems:**
  - **P1:** If `pytest` fails, `unittest` success can override and mark tests as passed.
    - Evidence: `:118-129`
  - **P2:** Missing `pytest` is treated as pass (no hard gate).
    - Evidence: `:135-136`
  - **P3:** Secret detection is simple substring matching with high false-negative/false-positive risk.
    - Evidence: `:141-157`

## Test Evidence Collected

Command run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_v2_*.py' -v
```

Result:
- Ran 186 tests
- 4 failures:
  - `tests/test_v2_executor.py::TestPlanExecutor::test_run_blocked_command`
  - `tests/test_v2_planner.py::TestPlanTask::test_fallback_on_bad_response`
  - `tests/test_v2_prompts.py::TestListTemplates::test_returns_all_templates`
  - `tests/test_v2_safety.py::TestSafetyPolicy::test_blocked_binary`

## Overall Judgement

`llm247_v2` has a strong architectural skeleton, but current implementation violates key AGENTS.md invariants in three places: **reviewable git workflow**, **least-privilege safety**, and **prompt governance consistency**.  
The most urgent fixes are in `agent.py`, `safety.py`, and `dashboard.py`.

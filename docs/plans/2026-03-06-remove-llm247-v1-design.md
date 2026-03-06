# Remove llm247 V1 Design

**Date:** 2026-03-06

## Goal

Remove the legacy `llm247` V1 runtime completely so the repository only exposes and validates `llm247_v2`.

## Scope

- Delete the full `src/llm247/` package.
- Delete legacy tests that import `llm247`.
- Delete legacy runtime scripts that launch or recover V1.
- Update repository documentation and project conventions to describe V2 as the only supported implementation.
- Preserve existing V2 code paths and verification commands.

## Non-Goals

- Renaming `llm247_v2` to a new Python package name.
- Changing V2 runtime behavior beyond removing V1 coexistence language and references.
- Migrating any V1 state data under `.llm247/`.

## Recommended Approach

Use a hard-delete strategy:

1. Remove all V1 Python modules and tests in one pass.
2. Remove scripts that only exist for V1 operation or V1 file recovery.
3. Replace coexistence documentation with V2-only documentation.
4. Run V2 verification and a repository-wide reference scan to confirm no supported path still depends on V1.

## Rationale

Keeping dead V1 code increases maintenance cost, leaves ambiguous runtime entry points, and makes project conventions internally inconsistent. Since the user explicitly wants full removal, a compatibility shell would preserve complexity without product value.

## Affected Areas

### Runtime

- `src/llm247/`
- `scripts/start.sh`
- `scripts/recover_autonomous.py`

### Tests

- All non-`test_v2_*` tests that import `llm247`

### Documentation

- `AGENTS.md`
- `README.md`

## Risks

### Hidden V1 references

Repository text, scripts, or tests may still mention `llm247`. A final `rg` sweep is required after deletion.

### Stale assumptions in project conventions

`AGENTS.md` currently documents V1/V2 coexistence and the legacy V2 naming convention for tests. Those conventions must be rewritten so future work does not preserve removed behavior.

## Verification

- `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_v2_*.py" -v`
- `npm run build` in `frontend/`
- `rg -n "\\bllm247\\b|src/llm247|test_(ark_client|autonomous|config|core|daemon|dashboard|logging|tasks|worker)\\.py" AGENTS.md README.md scripts src tests docs`

## Expected Outcome

After this change, the repository has a single supported agent implementation: `llm247_v2`. There is no runnable V1 code, no maintained V1 tests, and no supported script path that references the legacy package.

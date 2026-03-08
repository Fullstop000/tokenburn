# Proposal: Startup API Key Import

> Status: Superseded
> Created: 2026-03-09
> Decision: Implemented and merged in PR #62
> Scope: `scripts/start_v2.sh`, V2 CLI bootstrap, and model registry import logic
> Next Step: Keep the relevant design docs aligned with the merged implementation
> Related: [docs/design/dashboard.md](../design/dashboard.md), [docs/plans/2026-03-06-model-registry-and-routing.md](../plans/2026-03-06-model-registry-and-routing.md), [docs/archive/2026-03-09-startup-api-key-import.md](../archive/2026-03-09-startup-api-key-import.md)

## Summary

Operators can already register models through the dashboard, but first-run startup still requires manual setup.
This proposal adds one startup path that accepts an `api_key.yaml` file, parses one or more model entries, and imports them into the V2 model registry before bootstrap checks run.
The goal is to make `start_v2.sh` usable as a zero-dashboard bootstrap path for common single-model setups.

## Problem

Today, users who already have a provider config file must still open the dashboard and re-enter the same model details by hand.
That adds friction to local setup and makes scripted startup less useful.
It also creates a mismatch between the CLI startup workflow and the model registry workflow.

## Proposal

Add an optional startup-time import step:

- `scripts/start_v2.sh` accepts an optional `api_key.yaml` path for runtime commands
- `python -m llm247_v2` accepts `--api-key-file`
- startup parses a narrow YAML format compatible with the sample file in `/home/zht/roocode-wrapper/api_key.yaml`
- each parsed entry is normalized into a model registry record
- existing models with the same `model_type + endpoint + model_name` are updated in place; otherwise a new model is registered

The import should happen before bootstrap readiness checks so the imported LLM can satisfy setup requirements immediately.

## Why Now

The dashboard redesign made registry-based configuration more visible, but it did not solve CLI-first setup.
This is the smallest feature that closes that gap without inventing a second long-term config system.

## Risks and Open Questions

- The parser intentionally supports only a narrow YAML subset; malformed or more complex files should fail clearly.
- Import should not silently rewrite unrelated registry rows.
- Entry-point mapping must remain explicit: LLM imports map to `base_url`, embedding imports map to `api_path`.

## Exit Criteria

- `start_v2.sh` can accept an `api_key.yaml` path and pass it into V2 startup
- V2 startup imports compatible YAML entries before bootstrap checks
- re-importing the same file updates the same registry row instead of creating duplicates
- tests cover parsing, import, and CLI argument plumbing

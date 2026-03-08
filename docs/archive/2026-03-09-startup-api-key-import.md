# Plan: Startup API Key Import

> Status: Completed
> Created: 2026-03-09
> Completed: 2026-03-09
> PR: https://github.com/Fullstop000/sprout/pull/62
> Proposal: [docs/proposals/2026-03-09-startup-api-key-import.md](../proposals/2026-03-09-startup-api-key-import.md)

## Summary

Allow `scripts/start_v2.sh` and `python -m llm247_v2` to accept one `api_key.yaml` file and import its model definitions into the V2 model registry before bootstrap checks.

## Scope

- CLI argument plumbing for `--api-key-file`
- shell script support for forwarding one optional YAML path
- narrow YAML parsing compatible with the existing sample format
- idempotent registry import via upsert semantics
- tests for parsing, import, and startup argument handling

## Wireframe

Startup flow:

```text
start_v2.sh both /path/to/api_key.yaml
  -> python -m llm247_v2 --with-ui --api-key-file /path/to/api_key.yaml
    -> parse YAML entries
    -> register/update models in models.db
    -> run bootstrap readiness check
    -> continue normal startup
```

## Steps

1. Add failing tests for YAML parsing and import idempotency.
2. Add one import module that parses the narrow YAML shape and upserts models into `ModelRegistryStore`.
3. Add `--api-key-file` to the V2 CLI and invoke import before bootstrap checks.
4. Update `scripts/start_v2.sh` usage and forwarding for runtime commands.
5. Run targeted tests and update any touched design docs if behavior becomes part of the documented current system.

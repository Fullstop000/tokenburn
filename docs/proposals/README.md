# Proposals

`docs/proposals/` is the queue for ideas that are worth thinking about but are not approved implementation work yet.

## How To Read This Directory

- Order proposals by status first, then newest first within each status.
- Use date-prefixed filenames: `YYYY-MM-DD-<slug>.md`.
- Keep each proposal concise at the top: a reader should understand the decision needed from the metadata block and `Summary` section alone.
- Do not turn proposal files into task checklists. Once work is approved, create a plan in `docs/plans/`.

## Active Proposals

| Status | Proposal | Scope | Next Step |
|--------|----------|-------|-----------|
| `Approved for Plan` | [2026-03-07-human-agent-interaction.md](2026-03-07-human-agent-interaction.md) | Replace one-way `human_help_request` handoff with GitHub Issues + internal mirror | Plan at [docs/plans/2026-03-07-human-agent-interaction.md](../plans/2026-03-07-human-agent-interaction.md) |
| `Draft` | [2026-03-07-openclaw-memory-architecture.md](2026-03-07-openclaw-memory-architecture.md) | Benchmark Sprout memory architecture against OpenClaw's memory subsystem | Decide whether one narrow memory change is worth turning into a plan |
| `Draft` | [2026-03-07-lab.md](2026-03-07-lab.md) | Continuous lab environment for observing long-term agent evolution | Decide whether to fund Phase A (`Greenhouse`) and then write an implementation plan |
| `Review Needed` | [2026-03-07-e2e-testing.md](2026-03-07-e2e-testing.md) | Multi-layer end-to-end testing strategy for the V2 agent runtime | Decide the first deliverable and split it into one or more plans |

## Proposal Template

```md
# Proposal: <name>

> Status: Draft | Review Needed | Approved for Plan | Rejected | Superseded
> Created: YYYY-MM-DD
> Decision: <what decision is needed now>
> Scope: <one-line scope boundary>
> Next Step: <single concrete next action>
> Related: <links to design docs, plans, or sibling proposals>

## Summary

## Problem

## Proposal

## Why Now

## Risks and Open Questions

## Exit Criteria
```

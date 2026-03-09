# Plan: Dashboard Task PR and Live Token Visibility

> Status: Approved
> Created: 2026-03-09
> Proposal: [docs/proposals/2026-03-09-dashboard-task-pr-and-live-tokens.md](../proposals/2026-03-09-dashboard-task-pr-and-live-tokens.md)

## Goal

Make the Work surface trustworthy for active execution by showing live token costs, relevant PR state, and a clearer task detail reading order.

## Scope

- Persist in-progress execution metadata to `TaskStore`
- Enrich dashboard task payloads with PR metadata/status
- Update Work page task list/detail presentation
- Add regression tests for API shaping and execution progress persistence

## Non-Goals

- Redesign the overall Work navigation
- Introduce a GitHub webhook or background sync system
- Replace the current polling model

## Implementation Steps

1. Add failing tests for live task token persistence and PR metadata in dashboard payloads
2. Persist execution progress during the ReAct loop instead of only at task finalization
3. Add best-effort PR status lookup for dashboard task APIs
4. Update the Work page to show total tokens, PR status, and stacked description/events
5. Verify Python tests and frontend build

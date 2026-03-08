# Proposal: Realtime Execution Telemetry And Task/PR Linkage

> Status: Approved for Plan
> Created: 2026-03-09
> Decision: Approved; implementation is in progress in PR #61
> Scope: Execution observability, dashboard projections, git PR metadata persistence, task/PR cross-linking
> Next Step: Merge PR #61, complete the linked plan, then update the affected design docs
> Related: `docs/design/observability.md`, `docs/design/execution.md`, `docs/design/dashboard.md`, `docs/plans/2026-03-09-realtime-execution-telemetry-and-task-pr-linkage.md`

## Summary

Two reviewability gaps are currently visible in normal V2 runs.

First, token usage and LLM tool-selection activity are visible in terminal logs but do not surface to the dashboard in realtime. Second, when the agent opens a PR, the resulting task does not reliably retain the PR URL and the PR body does not include enough task metadata to form a bidirectional link.

This proposal fixes those gaps without redesigning the broader observability model.

## Problem

The current system only persists token totals onto the `Task` row after the full task finishes. That makes dashboard statistics lag behind real execution even though the shared `TokenTracker` already has the data.

Separately, the dashboard consumes `activity.jsonl`, but LLM tool-selection activity currently only appears as plain process logs from `llm247_v2.llm.client`. Those log lines never become observer events, so the dashboard has nothing realtime to render.

On the git side, PR creation succeeds, but the URL can stay trapped in loop-local state and observer events instead of being written back to `Task.pr_url`. The created PR body also lacks task identity fields such as task id and title, so humans cannot reliably navigate from the PR back to the originating task.

## Proposal

Implement one narrow fix set:

1. emit structured realtime execution telemetry for LLM usage and tool selection through `Observer`
2. make dashboard statistics and activity projections consume those realtime signals instead of waiting for task-final persistence
3. persist PR metadata back onto the task immediately after PR creation succeeds
4. enrich PR creation content with task identifiers so the PR references its originating task directly

The detailed event names, persistence strategy, and verification matrix belong in the plan.

## Why Now

These gaps directly weaken the product's stated pillars of human-friendly observability and reviewable control. They also make the new async review-first dashboard look stale during active execution, which undercuts the redesign.

## Risks and Open Questions

- whether realtime token totals should be derived from task rows, observer events, or LLM audit rows
- whether LLM tool-selection events belong under `LLM` or `Execution`
- how much PR metadata is enough without over-constraining future PR templates
- whether task backlinking should happen only on successful PR creation or also for failed attempts

## Exit Criteria

This proposal is complete when:

- dashboard token totals move during active execution instead of only after task completion
- dashboard activity shows LLM/tool-selection progress in realtime
- a successful PR write updates `Task.pr_url`
- the PR body includes enough task metadata to navigate back to the originating task

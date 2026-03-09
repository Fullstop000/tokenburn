# Proposal: Dashboard Task PR and Live Token Visibility

> Status: Approved for Plan
> Created: 2026-03-09
> Decision: Approved by direct implementation request
> Scope: Task list/detail layout, live token visibility, and PR status surfacing in the dashboard
> Next Step: Execute the linked implementation plan
> Related: `docs/design/dashboard.md`, `docs/design/observability.md`, `docs/plans/2026-03-09-dashboard-task-pr-and-live-tokens.md`

## Summary

The current Work surface still hides three pieces of execution evidence that operators need during review:

- task detail keeps description and events side by side instead of reading as one vertical narrative
- token usage is visible in logs but is not persisted to task rows until the task finishes
- task list/detail surfaces the PR URL only, with no status context

This proposal scopes a targeted dashboard correction rather than another broad layout redesign.

## Problem

The dashboard currently makes it harder to inspect active work than it should:

- live token spend looks broken because the store is updated only after execution ends
- operators cannot tell whether a linked PR is open, merged, or closed without leaving the dashboard
- task detail splits the story between adjacent description and event panels instead of one reading flow

## Proposal

Implement three linked changes:

1. persist execution progress back into the task store while the ReAct loop is still running, including branch, PR URL, and token counters
2. enrich dashboard task payloads with PR metadata/status for rows that already have a PR URL
3. restack task detail so description and events read top-to-bottom

## Expected Value

- active tasks show non-zero token cost as soon as LLM calls happen
- task list and detail give immediate PR review context
- task detail becomes easier to scan during async review

## Risks and Open Questions

- PR status enrichment must degrade safely when `gh` is unavailable or the PR URL is invalid
- live progress writes should stay lightweight enough for local polling

## Exit Criteria

- task token counters update before task completion
- aggregate total tokens reflect in-progress task usage after refresh
- Work task list and detail both show PR link plus status
- task detail stacks description and events vertically

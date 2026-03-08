# Plan: Realtime Execution Telemetry And Task/PR Linkage

> Status: Approved
> Created: 2026-03-09
> Proposal: [docs/proposals/2026-03-09-realtime-execution-telemetry-and-task-pr-linkage.md](../proposals/2026-03-09-realtime-execution-telemetry-and-task-pr-linkage.md)

## Goal

Fix two reviewability regressions in V2:

1. dashboard execution telemetry must update while a task is still running
2. task and PR metadata must link in both directions after PR creation

## Scope

**In scope:** `llm/client.py`, `execution/loop.py`, `execution/git_ops.py`, `agent.py`, dashboard API projections, and focused tests

**Out of scope:** a full observability architecture rewrite, websocket/live-push infrastructure, dashboard visual redesign, or changing unrelated git workflow rules

## Root Causes

### Realtime telemetry gap

- token totals are derived from persisted task rows
- task token fields are updated only at task finalization
- `llm_tool_call` information is logged through Python logging, not `Observer`
- dashboard activity reads `activity.jsonl`, so plain logger output is invisible there

### Task/PR backlink gap

- PR URL is stored in loop-local state but not reliably written back onto the `Task`
- PR creation body does not embed task identifiers or title
- observer records the PR event, but task detail and GitHub readers still lack a stable backlink

## Implementation

### 1. Add failing tests first

- add a regression test proving realtime stats can include in-flight token usage
- add a regression test proving activity includes an LLM tool-selection event
- add a regression test proving successful PR creation writes `Task.pr_url`
- add a regression test proving generated PR body includes task id and title metadata

### 2. Emit structured realtime LLM telemetry

- introduce one observer event for a completed LLM tool-selection turn
- include model name, tool count, prompt tokens, completion tokens, and total tokens
- emit it from the ReAct loop immediately after `generate_with_tools()` succeeds

### 3. Expose realtime token usage to dashboard APIs

- choose one authoritative source for in-flight totals
- keep cumulative task totals intact
- make `/api/stats` and `/api/summary` reflect active execution usage without waiting for task completion

### 4. Persist task PR metadata immediately

- make the execution result path expose final loop state back to the agent
- copy `branch_name` and `pr_url` from execution state onto the task before final task persistence
- keep observer PR events as supplementary audit evidence, not the only record

### 5. Enrich PR body backlink metadata

- prepend a stable task reference block to PR bodies
- include at least task id and task title
- preserve the self-exec prefix behavior already enforced by `GitWorkflow`

## Verification

- targeted unit tests for new telemetry and backlink behavior
- targeted dashboard API tests for realtime stats/summary behavior
- targeted git workflow tests for PR body generation
- keep frontend verification out of scope unless API shape changes force it

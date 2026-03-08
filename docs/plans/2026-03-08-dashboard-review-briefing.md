# Plan: Dashboard Review Briefing Redesign

> Status: In Progress
> Created: 2026-03-08
> PR: https://github.com/Fullstop000/sprout/pull/62
> Proposal: [docs/proposals/2026-03-08-dashboard-review-briefing.md](../proposals/2026-03-08-dashboard-review-briefing.md)

## Goal

Redesign the Sprout dashboard so the default experience supports async human review:

1. summarize what the agent has recently done
2. explain which changes matter and why
3. surface blockers and intervention points without leading with them
4. preserve one-click access to underlying evidence and control surfaces

## Scope

**In scope:** dashboard frontend information architecture, navigation hierarchy, homepage composition, supporting frontend data shaping, and any small API adjustments required to power the new homepage

**Out of scope:** changes to agent runtime behavior, changes to event emission semantics unrelated to homepage needs, full observability architecture refactors, authentication, or unrelated dashboard backend cleanup

## Design Direction

The redesigned dashboard should behave like an async review workspace, not a live monitoring console.

### Homepage Responsibilities

The homepage should answer these questions in order:

1. What has the agent accomplished recently?
2. Is anything blocked or unhealthy?
3. What changed that deserves inspection?
4. Where should I go next if I want details or need to intervene?

### Homepage Sections

#### 1. Briefing

Show a compact summary block that combines:

- a small set of structured signals with high decision value
- a short natural-language handoff summary
- lightweight runtime status metadata such as pause state, freshness, and setup readiness
- a very small statistics strip for cumulative context

The structured signals should be concise rather than decorative. Avoid large metric walls.

The retained statistics should favor long-horizon context over vanity metrics. The first version should include:

- cumulative input tokens
- cumulative output tokens
- recent completions
- current blockers

#### 2. What Changed

Render a curated recent-changes feed rather than a raw activity log. Each item should communicate:

- what happened
- why it matters
- what entity it affected
- where the operator can drill down next

Examples of homepage-worthy changes include:

- task completed
- verification failed
- task entered `needs_human`
- new inbox message waiting for reply
- initialization or model setup issue
- cycle completed with meaningful outcomes

#### 3. Needs Attention

Surface pending operator work in a compact, prioritized block:

- blockers that stop useful progress
- unresolved human-help tasks
- waiting inbox threads
- setup issues preventing normal operation

This section is for routing, not deep reading.

#### 4. Continue Reading

Provide clear entry points into:

- `Work`
- `Inbox`
- `Discovery`
- `Memory & Audit`
- `Control`

Each destination should have a short description so the homepage teaches the information architecture.

### Homepage Wireframe

The first screen should read like a briefing before it reads like a tool.

```text
+----------------------------------------------------------------------------------+
| Sprout Dashboard                                                                 |
| Async review workspace                                paused/live · updated 2m ago |
+----------------------------------------------------------------------------------+
| Briefing                                                                        |
| +---------------------------+ +-----------------------------------------------+ |
| | Structured Signals        | | Natural-Language Handoff                      | |
| | - input tokens            | | "Since your last visit, the agent finished   | |
| | - output tokens           | |  3 tasks, queued 2 new tasks, and is blocked | |
| | - recent completions      | |  on one verification failure in dashboard..."| |
| | - current blockers        | |                                               | |
| +---------------------------+ +-----------------------------------------------+ |
+----------------------------------------------------------------------------------+
| What Changed                                                                     |
| +------------------------------------------------------------------------------+ |
| | [Task completed] Dashboard API cleanup                                        | |
| | Why it matters: unblocks follow-up work on homepage projections               | |
| | Related: task-123 · cycle-88                                   Open task -> | |
| +------------------------------------------------------------------------------+ |
| +------------------------------------------------------------------------------+ |
| | [Needs human] Verification failed for frontend build                          | |
| | Why it matters: review flow is ready but build evidence is incomplete         | |
| | Related: task-124 · audit-451                              Open audit log -> | |
| +------------------------------------------------------------------------------+ |
+--------------------------------------------------+-------------------------------+
| Needs Attention                                  | Continue Reading              |
| - blocked task needing decision                  | Work            task details  |
| - waiting inbox thread                           | Inbox           async dialog  |
| - setup issue / missing model                    | Discovery       new findings  |
|                                                  | Memory & Audit  evidence      |
|                                                  | Control         settings      |
+--------------------------------------------------+-------------------------------+
```

This wireframe is intentionally content-first:

- the briefing owns the top of the page
- the explained timeline is the main body
- attention items are visible but secondary
- deeper tools remain easy to reach without dominating first impression

## Information Architecture Changes

### Navigation

Reframe navigation so the homepage is the primary summary surface and other pages are specialized deeper views. Keep the number of top-level destinations unchanged unless implementation reveals one clear merge opportunity.

### Page Roles

- `Overview` becomes the async review briefing homepage
- `Work` focuses on tasks, task details, and execution flow
- `Inbox` focuses on human-agent async conversation
- `Discovery` focuses on newly discovered opportunities and source context
- `Memory & Audit` focuses on evidence, activity detail, and audit trails
- `Control` focuses on configuration, model setup, directives, and manual actions

## Visual Simplification Rules

- reduce visual dependence on repeated card containers
- remove duplicated runtime/bootstrap/task state summaries from the homepage
- use hierarchy, spacing, and typography to separate summary from evidence
- make homepage content readable in one pass before any scrolling if possible
- avoid generic dark-console aesthetics and avoid metrics-dashboard tropes

## Data And API Work

Review the current dashboard data flow and determine whether the homepage can be powered by:

- existing task, cycle, help-center, thread, activity, and bootstrap endpoints with client-side projection
- or one dedicated summary endpoint if the current frontend must otherwise over-fetch and over-derive

Prefer the smallest backend change that yields a trustworthy summary model.

If a new payload is required, it should provide:

- structured briefing signals
- cumulative token statistics
- recent meaningful changes
- attention items
- freshness metadata

## Implementation Tasks

1. Audit current homepage content and map each existing block to one of: keep, merge, move, or remove.
2. Define the homepage view model for `Briefing`, `What Changed`, `Needs Attention`, and `Continue Reading`.
3. Decide whether the view model is assembled client-side or through one new API response.
4. Redesign the dashboard shell to reduce chrome and support a content-first homepage.
5. Rebuild `OverviewPage` to match the new briefing structure.
6. Update related components or add focused new ones for summary signals, explained change items, and attention rows.
7. Adjust secondary page entry points and labels so they align with the new hierarchy.
8. Update tests covering homepage rendering and any API payload changes.
9. Update `docs/design/dashboard.md` after implementation.

## Verification

Before closing the work:

- run the frontend test/build path needed to verify the dashboard still compiles
- verify the redesigned homepage loads with realistic empty, active, and blocked states
- verify every homepage drill-down target reaches a valid deeper view
- verify the briefing does not duplicate raw data blocks already visible lower on the page
- verify the homepage still exposes essential control and setup states without becoming control-first

## Completion Notes

When implementation begins through a PR:

- update this plan status to `In Progress`
- add the PR URL

When implementation merges:

- update this plan to `Completed`
- move it to `docs/archive/`
- mark the proposal as `Superseded`
- update `docs/design/dashboard.md` to describe the shipped design

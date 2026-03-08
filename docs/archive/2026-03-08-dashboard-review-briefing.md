# Plan: Dashboard Review Briefing Redesign

> Status: Completed
> Created: 2026-03-08
> Completed: 2026-03-09
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
| | [Needs review] Verification failed on model registry flow                     | |
| | Why it matters: bootstrap remains blocked until this is resolved             | |
| | Related: task-456                                                Review ->  | |
| +------------------------------------------------------------------------------+ |
+----------------------------------------------------------------------------------+
| Needs Attention                           | Continue Reading                    |
| +--------------------------------------+ | +---------------------------------+ |
| | - blocked task needing answer        | | | Work           task execution   | |
| | - inbox thread waiting for reply     | | | Inbox          human threads    | |
| | - setup issue                        | | | Discovery      new opportunities | |
| +--------------------------------------+ | | Memory & Audit evidence trails   | |
|                                          | | Control        config/actions    | |
|                                          | +---------------------------------+ |
+----------------------------------------------------------------------------------+
```

## Data Requirements

The redesign may require one lightweight summary-oriented API or a frontend view-model layer that composes:

- task list
- task details for highlighted items
- recent observer activity
- help-center tasks
- inbox waiting threads
- bootstrap/setup status
- cumulative statistics such as token usage

The homepage should not make the frontend infer too much meaning from raw activity events on its own.

## Implementation Order

1. Define the homepage information model and required data contracts.
2. Rework the dashboard shell and homepage layout around `Briefing`, `What Changed`, `Needs Attention`, and `Continue Reading`.
3. Update secondary pages so they feel like deeper reading surfaces rather than equal-priority console tabs.
4. Refine error states, empty states, and loading behavior to match the async review model.
5. Validate the redesign in realistic data conditions and update `docs/design/dashboard.md`.

## Verification

The redesign is complete when:

- the homepage clearly communicates recent accomplishments, blockers, and meaningful recent changes
- `Work`, `Inbox`, `Discovery`, `Memory & Audit`, and `Control` feel like deeper views with distinct responsibilities
- the interface works in empty, active, and blocked system states
- navigation between homepage summaries and detailed evidence is clear and fast
- the resulting implemented system is documented in `docs/design/dashboard.md`

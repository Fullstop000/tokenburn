# Plan: Dashboard Layout Refactor

> Status: Pending
> Created: 2026-03-07
> Related: [docs/design/dashboard.md](../design/dashboard.md), [docs/design/observability.md](../design/observability.md)

## Goal

Redesign the dashboard so the operator can understand the agent's state, current work, discovery decisions, and control actions without hunting across unrelated tabs. At the same time, break the frontend out of the current monolithic `frontend/src/App.tsx` into feature-scoped modules.

## Why This Change

The current dashboard works as a collection of tabs, but not as a control plane:

- Critical status is fragmented across `Tasks`, `Cycles`, `Activity`, `Help`, and `Models`.
- Discovery reasoning exists in observer events, but it is only visible as generic activity rows.
- The frontend implementation is concentrated in one large file (`frontend/src/App.tsx`), which makes layout changes risky and slows iteration.
- The current navigation is data-type oriented, not operator-job oriented.

This conflicts with the project requirement that human observability and control are first-class.

## Non-Goals

- Replace the backend HTTP server or API transport.
- Redesign the visual identity from scratch.
- Change task, cycle, model, or directive data models unless required for the new dashboard surfaces.
- Implement auth, multi-user support, or remote access controls.

## Information Architecture After

The dashboard should be organized around operator workflows, not storage tables.

### Primary navigation

Use five top-level sections:

1. `Overview`
2. `Work`
3. `Discovery`
4. `Memory & Audit`
5. `Control`

### Section responsibilities

#### 1. Overview

The landing surface. It should answer:

- Is the runtime healthy?
- Is setup complete?
- What is the agent doing now?
- Is human action required?

Widgets:

- runtime status / bootstrap banner
- key stats cards
- active task summary
- latest cycle summary
- unresolved help requests preview
- recent high-signal activity preview

#### 2. Work

Execution-oriented views:

- task list
- task detail
- cycle history
- execution trace / verification / task events

This groups together what is currently split between `Tasks` and `Cycles`.

#### 3. Discovery

A dedicated surface for discovery reasoning:

- selected discovery strategy
- raw candidates
- heuristic scores
- LLM value scores
- filtered-out candidates with reasons
- final queued tasks

This section should make the discovery funnel legible end-to-end instead of forcing operators to reconstruct it from generic activity events.

#### 4. Memory & Audit

Long-horizon introspection:

- experiences
- LLM audit feed
- full LLM audit detail
- global activity stream

`Activity` belongs here as an audit surface, not as the primary way to understand discovery.

#### 5. Control

Operator actions and mutable runtime state:

- pause / resume
- directive editor
- model registry
- model bindings
- manual task injection

The setup / bootstrap CTA should route here when initialization is incomplete.

## Page Layout Principles

### Overview-first, drill-down second

The first screen should summarize the system. Detailed tables and logs should be one click away, not the first thing the operator sees.

### Separate “what is happening” from “why it happened”

- `Overview` and `Work` focus on live state and outcomes.
- `Discovery` and `Memory & Audit` focus on reasoning and history.

### Reduce mixed-content tabs

Do not mix unrelated controls and read-only observability in the same page unless they serve one operator workflow.

### Preserve direct access to deep detail

Task detail, audit detail, and model edit flows must remain reachable without losing context.

## Frontend Module Layout After

Refactor `frontend/src/` by feature:

```text
frontend/src/
├── app/
│   ├── DashboardApp.tsx
│   ├── routes.ts
│   └── layout/
│       ├── DashboardShell.tsx
│       ├── DashboardSidebar.tsx
│       ├── SectionHeader.tsx
│       └── StatusBanner.tsx
├── features/
│   ├── overview/
│   │   ├── OverviewPage.tsx
│   │   ├── components/
│   │   └── hooks.ts
│   ├── work/
│   │   ├── WorkPage.tsx
│   │   ├── TaskDetailPanel.tsx
│   │   ├── CyclesPanel.tsx
│   │   └── components/
│   ├── discovery/
│   │   ├── DiscoveryPage.tsx
│   │   ├── DiscoveryFunnel.tsx
│   │   ├── DiscoveryCandidateList.tsx
│   │   └── selectors.ts
│   ├── memory/
│   │   ├── MemoryAuditPage.tsx
│   │   ├── ActivityFeed.tsx
│   │   ├── LlmAuditPanel.tsx
│   │   └── ExperiencePanel.tsx
│   └── control/
│       ├── ControlPage.tsx
│       ├── DirectivePanel.tsx
│       ├── ModelsPanel.tsx
│       ├── HelpCenterPanel.tsx
│       └── InjectTaskPanel.tsx
├── api/
│   ├── client.ts
│   ├── dashboardApi.ts
│   └── queries.ts
├── components/
│   ├── activity/
│   ├── cards/
│   ├── task/
│   └── ui/
├── hooks/
│   ├── useDashboardPolling.ts
│   └── useBootstrapStatus.ts
└── types/
    └── dashboard.ts
```

## Data Shaping Changes

The current frontend reads raw API payloads directly in `App.tsx`. The refactor should introduce lightweight selectors/helpers so feature pages consume view models rather than low-level payloads.

Examples:

- discovery activity events → `DiscoveryStage[]`
- task detail payload → `TaskDetailViewModel`
- bootstrap status + stats + help requests → `OverviewSnapshot`

## Backend Support Needed

The current `/api/activity` endpoint is enough for a first pass, but the discovery page will be much cleaner if the backend exposes a discovery-focused projection.

Preferred additions:

- `GET /api/discovery` → latest discovery funnel grouped by cycle and candidate
- `GET /api/overview` → bootstrap status + stats + active task + unresolved help summary

If these endpoints are deferred, the frontend may initially derive the page from existing `/api/activity`, `/api/stats`, `/api/cycles`, `/api/help-center`, and `/api/tasks` responses.

## Implementation Phases

### Phase 1: Layout shell and page extraction

- Introduce app shell, sidebar/top nav, and feature page boundaries.
- Move code out of `App.tsx` without changing behavior.

### Phase 2: Overview and Control consolidation

- Build the new `Overview` landing page.
- Move setup, model registry, directive controls, and task injection under `Control`.

### Phase 3: Work surface cleanup

- Merge task and cycle workflows into one `Work` section.
- Keep task detail as the main drill-down path.

### Phase 4: Discovery surface

- Add a dedicated discovery page.
- Surface strategy, candidate funnel, filter reasons, and queued outcomes.
- Add backend discovery projection if activity-derived shaping is too brittle.

### Phase 5: Memory & Audit cleanup

- Move activity, experiences, and LLM audit into a coherent audit surface.
- Preserve current detail views while improving navigation.

## Verification

- Frontend build passes after each extraction step.
- Existing dashboard API tests still pass.
- Browser-based E2E/manual verification covers:
  - bootstrap-required state routes operator to `Control`
  - operator can find active task and unresolved help from `Overview`
  - operator can inspect discovery funnel in `Discovery`
  - operator can reach task detail and LLM audit detail without losing context
  - operator can pause/resume and edit models from `Control`

## Exit Criteria

- `frontend/src/App.tsx` is reduced to app bootstrap and route composition.
- Dashboard navigation is organized by operator workflow instead of storage type.
- Discovery decisions are visible in a dedicated page, not only in generic activity rows.
- The design docs are updated to describe the implemented layout and any new endpoints.

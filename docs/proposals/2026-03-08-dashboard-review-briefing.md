# Proposal: Dashboard Review Briefing Redesign

> Status: Approved for Plan
> Created: 2026-03-08
> Decision: Approved; implementation is in progress in PR #62
> Scope: Dashboard information architecture, homepage priorities, navigation hierarchy, and visual design direction
> Next Step: Merge PR #62, complete the linked plan, and then update `docs/design/dashboard.md`
> Related: `docs/design/dashboard.md`, `docs/design/observability.md`, `docs/design/project.md`, `docs/plans/2026-03-08-dashboard-review-briefing.md`

## Summary

Sprout's dashboard currently behaves like a generic live operations console: it foregrounds cards, runtime state, and raw activity in a way that assumes a human operator is watching continuously.

That does not match the product's current collaboration model. Sprout is primarily an async human-agent system. People enter the dashboard to understand what the agent has been doing, identify important changes, and intervene only when needed.

This proposal repositions the dashboard around that reality. The homepage becomes a review briefing: concise structured signals, a short natural-language handoff, and an explained timeline of meaningful recent changes.

## Problem

The current dashboard has three related problems:

- it optimizes for continuous monitoring rather than async review
- it gives too much visual weight to low-context status cards and raw event lists
- it repeats the same system state in multiple places instead of establishing one clear narrative

As a result, a human opening the dashboard after some time away still has to synthesize the story themselves:

- what the agent accomplished recently
- what changed that actually matters
- where the agent is blocked
- where to click next for evidence or intervention

The interface exposes data, but it does not yet function as an effective handoff.

## Proposal

Redesign the dashboard around one primary user goal:

1. help a human quickly understand what the agent has recently done
2. provide direct paths into the evidence behind that summary
3. surface intervention points only after context is established

The redesign should make four structural changes.

First, replace the current overview page with a briefing-style homepage built from four sections:

- `Briefing` — compact structured signals plus a short natural-language handoff
- `What Changed` — an explained timeline of meaningful recent changes rather than a raw activity dump
- `Needs Attention` — a compact list of blockers, unresolved human requests, and waiting inbox threads
- `Continue Reading` — clear entry points into deeper task, inbox, discovery, audit, and control views

Second, reframe navigation around depth rather than parity. The homepage becomes the default summary surface, while `Work`, `Inbox`, `Discovery`, `Memory & Audit`, and `Control` become deeper reading and intervention surfaces.

Third, simplify the visual system. Reduce the card-heavy control-console style, establish a clearer reading hierarchy, and support both structured data and narrative summaries without making the page feel like a metrics wall.

Fourth, treat the homepage timeline as a projection of important state changes rather than a dump of raw observer events. The UI should translate low-level events into human-readable changes with explicit links to the relevant task, thread, cycle, or audit artifact.

## Expected Value

- faster understanding for humans re-entering the system after time away
- better alignment between dashboard design and Sprout's async collaboration model
- lower cognitive load on the homepage without removing observability depth
- clearer separation between summary, evidence, and control surfaces
- a dashboard that feels purpose-built for agent handoff instead of generic admin monitoring

## Risks and Open Questions

- whether the current backend projections can support a trustworthy briefing without additional API shaping
- how much natural-language summarization should be derived client-side versus returned directly by the server
- how aggressively the homepage should filter low-level events before operators feel they are losing fidelity
- whether the redesigned navigation should remain sidebar-based or move to a lighter top-level pattern

The redesign should keep evidence one click away so that summarization never becomes opacity.

## Exit Criteria

This proposal is ready to close when:

- the dashboard homepage is explicitly optimized for async review rather than continuous monitoring
- the homepage combines structured signals and natural-language handoff in one coherent briefing
- the homepage timeline presents meaningful recent changes with context and drill-down links
- secondary pages have clearer roles as deeper reading or intervention surfaces
- `docs/design/dashboard.md` reflects the implemented information architecture and design intent

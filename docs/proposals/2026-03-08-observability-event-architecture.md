# Proposal: Observability Event Architecture

> Status: Draft
> Created: 2026-03-08
> Decision: Pending
> Scope: Observability, dashboard projections, event storage, module contracts
> Next Step: Review proposal and, if approved, execute the linked implementation plan
> Related: `docs/design/observability.md`, `docs/design/execution.md`, `docs/design/architecture.md`, `docs/plans/2026-03-08-observability-event-architecture.md`

## Summary

Sprout's observability model needs a clearer split between event emission, event storage, event correlation, and event presentation. The current `Observer` is already a strong single emission point, but downstream consumers still reconstruct module views through ad hoc projections over raw events.

This proposal introduces a stricter architecture: `Observer` remains the standard reporting interface, each module defines an explicit event catalog, correlations become first-class, and dashboard pages consume module-scoped projections instead of hardcoded phase/action filters.

## Problem

The current system mixes four concerns:

- standard event emission
- raw event persistence
- cross-entity event correlation
- page-level presentation logic

That makes it difficult to tell whether a missing artifact is caused by no event emission, no storage, no correlation rule, or no projection support. Discovery is the clearest example: event-level discovery history is visible, but task-owned artifacts such as execution trace are not part of an explicit discovery correlation model.

## Proposal

Adopt a four-layer observability architecture:

1. `Observer` remains the single standard reporting interface
2. each module defines its own event catalog and event semantics
3. storage and correlation become explicit architectural responsibilities
4. dashboard views consume stable module projections rather than raw event filtering logic

The detailed event catalogs, correlation rules, migration order, and verification strategy belong in the implementation plan.

## Expected Value

- clearer module ownership over event semantics
- easier dashboard evolution without coupling UI to logging internals
- explicit correlation between events, tasks, cycles, threads, and LLM audit rows
- more reliable human inspection because each module view has a defined contract

## Risks and Open Questions

- how much schema formalization is necessary before the design becomes too heavy
- whether event catalogs should live only in docs or also in code
- whether correlations should be materialized, computed on demand, or introduced incrementally
- which module should be the first migration exemplar

Discovery remains the best first exemplar because it already exposes the mismatch between raw event streams and task-level observability artifacts.

## Exit Criteria

This proposal is ready to advance when:

- the four-layer split is accepted
- module event catalogs are accepted as the source of truth for event semantics
- correlation is accepted as a first-class concern
- the linked implementation plan is approved as the execution spec

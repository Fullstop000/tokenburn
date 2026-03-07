# V2 Architecture Overview

> Last updated: 2026-03-07

## Subsystems

Seven subsystems, each with a single responsibility:

| Subsystem | Responsibility | Key Abstractions |
|-----------|---------------|-----------------|
| **Core** | Shared data models and immutable rules | `Task`, `TaskPlan`, `Directive`, `Constitution` |
| **LLM** | Language model communication and prompt management | `LLMClient`, prompt templates, `TokenTracker` |
| **Storage** | SQLite persistence across all time horizons | `TaskStore`, `ExperienceStore`, `ModelRegistry` |
| **Observability** | Unified event emission to all sinks | `Observer` |
| **Discovery** | Task candidate generation and ranking | `DiscoveryPipeline`, `ExplorationMap`, `InterestProfile` |
| **Execution** | Plan, execute, verify, and ship changes | `Planner`, `Executor`, `Verifier`, `GitOps` |
| **Dashboard** | HTTP control plane and frontend | REST API, web UI |

## Dependency Flow

```
[ Dashboard ]   [ CLI ]
       ↓            ↓
    [ Agent — cycle orchestrator ]
           ↙               ↘
   [ Discovery ]       [ Execution ]
           ↘               ↙
    [ Core / LLM / Storage / Observability ]
            (shared foundation)
```

Rules:
- Discovery and Execution are independent — neither depends on the other.
- Both depend downward on Core, LLM, Storage, and Observability.
- The Agent orchestrates them; it does not implement their logic.
- Dashboard and CLI are driving adapters — they only call into Agent.

## The Cycle

Every cycle is a complete unit of work. The agent runs cycles indefinitely until paused or budget-exhausted.

```
┌─────────────────────────────────────────────────────────┐
│                     One Agent Cycle                      │
│                                                         │
│  1. Load Directive    ─── paused? → sleep and retry     │
│  2. Load Constitution ─── immutable safety rules        │
│  3. DISCOVER          ─── select strategy → scan →      │
│                           evaluate → rank → queue       │
│  4. EXECUTE           ─── pick top task → plan (LLM) →  │
│                           constitution check → worktree │
│                           → execute steps → verify      │
│  5. SHIP              ─── commit → push → create PR     │
│  6. LEARN             ─── extract learnings → store     │
│  7. OBSERVE           ─── emit events to all handlers   │
│                                                         │
│  (sleep poll_interval, then repeat)                     │
└─────────────────────────────────────────────────────────┘
```

## Memory Stack

The agent has six layers of memory, from immediate to permanent:

| Layer | Module | Storage | Scope | Purpose |
|-------|--------|---------|-------|---------|
| **Event stream** | Observer | `activity.log`, `activity.jsonl` | Instant | Real-time monitoring (`tail -f`) |
| **LLM audit trail** | LLMAuditLogger | `llm_audit.jsonl` | Instant | Full prompt/response for every LLM call |
| **Task history** | TaskStore | `tasks.db` | Per-task | Status, plan, execution log, costs, errors |
| **Exploration map** | ExplorationMap | `exploration_map.json` | Cross-cycle | Which areas explored, which strategies worked |
| **Interest profile** | InterestProfile | `interest_profile.json` | Cross-cycle | What the agent is curious about, derived from experience + exploration |
| **Experience** | ExperienceStore | `experience.db` | Permanent | Patterns, pitfalls, insights, techniques. See [experience.md](experience.md). |

No layer is redundant. Each serves a different time horizon and consumer:
- **Event stream + LLM audit**: for human real-time review ("what is the agent doing right now?")
- **Task history**: for human post-mortem review ("what happened with task X?")
- **Exploration map**: for the agent itself ("where should I look next?")
- **Interest profile**: for the agent itself ("what am I curious about?")
- **Experience**: for the agent itself ("what did I learn that applies here?")

## Module Design Docs

| Module | Design Doc |
|--------|------------|
| **Architecture evolution** | **[evolution.md](evolution.md)** — five cognitive layers, phased roadmap |
| Overall architecture | this file |
| Core (models, constitution, directive) | [core.md](core.md) |
| LLM client + prompts | [llm.md](llm.md) |
| Storage (TaskStore) | [storage.md](storage.md) |
| Observability | [observability.md](observability.md) |
| Discovery | [discovery.md](discovery.md) |
| Execution & safety | [execution.md](execution.md) |
| Experience | [experience.md](experience.md) |
| Dashboard | [dashboard.md](dashboard.md) |

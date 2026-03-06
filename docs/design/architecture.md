# V2 Architecture Overview

> Last updated: 2026-03-05

## Module Map

```
src/llm247_v2/
├── __init__.py              # Package summary and layout docs
├── __main__.py              # CLI entry point (imports from submodules)
├── agent.py                 # Main orchestrator: the cycle loop
│
├── core/                    # Shared base layer
│   ├── __init__.py
│   ├── models.py            # Core data models (Task, Directive, TaskPlan, CycleReport)
│   ├── constitution.py      # Immutable principles — the agent's DNA
│   └── directive.py         # Runtime behavior control (paused, focus, forbidden paths)
│
├── llm/                     # LLM client + prompt templates
│   ├── __init__.py
│   ├── client.py            # LLM protocol + Ark adapter + TokenTracker + AuditLogger
│   └── prompts/
│       ├── __init__.py      # Template loader + renderer
│       ├── plan_task.txt
│       ├── assess_value.txt
│       ├── extract_learnings.txt
│       ├── discover_stale_area.txt
│       ├── discover_deep_review.txt
│       ├── discover_llm_guided.txt
│       └── discover_web_search.txt
│
├── storage/                 # SQLite persistence
│   ├── __init__.py
│   ├── store.py             # Tasks/events/cycles
│   └── experience.py        # Long-term memory and learning extraction
│
├── observability/           # Event observation layer
│   ├── __init__.py
│   └── observer.py          # Centralized event system (log, JSONL, SQLite, console)
│
├── discovery/               # Task discovery pipeline
│   ├── __init__.py
│   ├── pipeline.py          # Strategy orchestration and candidate ranking
│   ├── exploration.py       # ExplorationMap — tracks visited areas
│   ├── value.py             # Value assessment — heuristic + LLM scoring
│   └── interest.py          # Interest profile + issue discovery sources
│
├── execution/               # Planning and execution pipeline
│   ├── __init__.py
│   ├── planner.py           # LLM-driven execution plan generation
│   ├── executor.py          # Safe action execution (edit, create, run, delete)
│   ├── verifier.py          # Post-execution verification (syntax, tests, secrets)
│   ├── git_ops.py           # Git workflow (worktree isolation, branch, commit, push, PR)
│   └── safety.py            # Command allowlist + path protection
│
└── dashboard/               # HTTP control plane
    ├── __init__.py
    └── server.py            # Dashboard server and API
```

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

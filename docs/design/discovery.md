# Discovery Module Design

> Module: `src/llm247_v2/discovery/`
> Last updated: 2026-03-05

## Purpose

The discovery module is responsible for finding meaningful engineering tasks in the repository. It answers the question: "What should the agent work on next?" It balances autonomous exploration with human-directed focus, and ensures the agent doesn't repeatedly scan the same areas.

## Architecture

Task discovery uses a five-layer architecture:

### 1. Exploration Module (`exploration.py`)

Selects a discovery strategy based on what areas are under-explored, what strategies have historically been productive, and what the directive focuses on.

Twelve strategies:
- `todo_sweep` — scan for TODO/FIXME/HACK comments
- `test_coverage` — find untested modules
- `change_hotspot` — find frequently modified files that may need refactoring
- `complexity_scan` — find complex functions/classes
- `stale_area` — find modules untouched for a long time
- `deep_module_review` — deep LLM review of a single module
- `dependency_review` — check for outdated or risky dependencies
- `llm_guided` — open-ended LLM exploration of the codebase
- `github_issues` — pull from GitHub issue tracker
- `dep_audit` — run `pip audit` for known CVEs
- `web_search` — LLM-powered analysis of stack for advisories and best practices
- `interest_driven` — generate tasks from the agent's evolved interest profile

The `ExplorationMap` tracks which areas have been scanned with which strategies, and how many tasks each yielded. This prevents the agent from re-scanning the same files every cycle.

### 2. Interest Module (`interest.py`)

The agent's curiosity engine. Builds an `InterestProfile` from three signals:
- (a) directive `focus_areas` — human-directed, highest priority
- (b) experience patterns — areas where the agent has been productive (from ExperienceStore stats and tags)
- (c) exploration yield — strategies/areas that historically produce high-value tasks

The `InterestProfile` guides `interest_driven` and `web_search` discovery. It decays over time and is boosted when an interest produces tasks.

### 3. Issue Sources (`interest.py`)

Four external/semi-external issue pipelines:
- `github_issues` — pulls from `gh issue list`, maps labels to priority
- `dep_audit` — runs `pip audit` for known CVEs in dependencies
- `web_search` — LLM-powered analysis of the stack for security advisories, deprecations, and best practices
- `interest_driven` — generates tasks from the agent's evolved interest profile

### 4. Value Module (`value.py`)

Two-tier scoring to filter and rank discovered candidates:

1. **Fast heuristic pass** — scores severity, directive alignment, scope, and actionability. Filters out obvious low-value candidates without an LLM call.
2. **LLM deep assessment** — ranks top heuristic candidates on impact, feasibility, risk, and alignment. Produces the final ordered list.

### 5. Decision Logging

Every candidate, every score, and every rejection reason is emitted through Observer so humans can trace the full discovery funnel:

```
raw candidates → heuristic filter → LLM assessment → final selection → queue
```

## Pipeline Flow

```
directive + constitution + interest profile
          │
          ▼
  ExplorationMap.select_strategy()
          │
          ▼
  run discovery strategy (scan / issue source)
          │
          ▼
  raw candidates (Task list)
          │
          ▼
  ValueModule.heuristic_filter()
          │
          ▼
  ValueModule.llm_assess() [top candidates only]
          │
          ▼
  ranked Task list → insert into store as QUEUED
```

## Design Constraints

- **Exploration map is updated every cycle** — even if no tasks are found, the map records that an area was scanned so the agent doesn't revisit it immediately.
- **Discovery is capped** — if the queue already has enough tasks (`queued_count` threshold), discovery is skipped to avoid runaway task accumulation.
- **Deduplication by title** — tasks with titles matching existing tasks in the store are silently dropped before queuing.

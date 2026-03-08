# Agent Guide

Project-specific rules for navigating and contributing to this codebase.
For universal coding, git, and testing standards, see [CONVENTIONS.md](CONVENTIONS.md).

---

## Mission

Sprout is an autonomous, self-evolving intelligence that builds deep understanding of its world, pursues goals across time, communicates with humans as partners, and deliberately improves its own capabilities.

It is not just an automation runtime. It is an attempt to build an agent that compounds its usefulness through learning, reflection, and self-modification while remaining reviewable and controllable by humans.

## The Five Pillars

These are project-level invariants. Violating any one of them means the system is architecturally wrong.

| Pillar | What it means |
|--------|--------------|
| **Autonomous Multi-Modal Operation** | Operates continuously; chooses highest-value work each cycle. Every token spent should produce a concrete artifact. |
| **Self-Evolving Through Learning** | Extracts learnings from success and failure, stores them persistently, retrieves them when relevant. Gets better over time. |
| **Self-Modification** | Improves its own code through the same reviewable workflow used for any other code. Its own implementation is not privileged. |
| **Human-Friendly Observability** | Humans can inspect what the agent is doing, has done, and why. Dashboard, logs, and audit trails are first-class requirements. |
| **Reviewable and Controllable** | Every meaningful action is reviewable after the fact and controllable in advance. Pause, redirect, constrain, or stop — the runtime must respect these immediately. |

---

## Immutable Guardrails

Read these first. They cannot be overridden by any task or instruction.

- `constitution.md` and `safety.py` are immutable — never modify them
- New ideas belong in `docs/proposals/`, not `docs/design/` or `docs/plans/`
- Significant approved changes require a plan in `docs/plans/` before code is written

## Worktree Requirement

Use an isolated git worktree for implementation work.

- Feature work, bug fixes, plan execution, multi-file code changes, and any work expected to end in a commit or PR must start in a dedicated worktree
- Follow the `using-git-worktrees` superpower practice: prefer the project-local `.worktrees/` directory and verify it is ignored before creating a worktree
- Keep the primary workspace on `main` unless the user explicitly asks for a different workflow
- Pure exploration, read-only investigation, and small documentation or configuration edits may stay in the primary workspace when no isolated implementation branch is needed

---

## Where to Start

Before making any project-level change, read the relevant authoritative docs:

| Doc | Covers |
|-----|--------|
| `docs/design/project.md` | Mission, pillars, repository-wide conventions |
| `docs/design/architecture.md` | Subsystems, dependency flow, agent cycle, memory stack |
| `docs/design/core.md` | Data models (Task, TaskPlan), constitution, directive |
| `docs/design/execution.md` | Planner, executor, verifier, safety, git workflow |
| `docs/design/observability.md` | Logs, audit trail, human review protocol |
| `docs/design/evolution.md` | Roadmap and long-range architecture |

---

## Documentation Decision Flow

When touching docs, decide by state — not by topic:

1. **Describing the current implemented system** → update `docs/design/<module>.md`
2. **Have a new idea, not yet approved** → create `docs/proposals/YYYY-MM-DD-<slug>.md`
3. **Work is approved, implementation is next** → create `docs/plans/YYYY-MM-DD-<slug>.md` before writing code
4. **Plan is fully implemented and verified** → move it unchanged to `docs/archive/YYYY-MM-DD-<slug>.md`
5. **Implementation changed the system** → update the affected `docs/design/` files before closing the work

```
idea → proposal → plan → [implement] → archive
                                    ↘
                              update docs/design/
```

---

## Documentation Layout

```
docs/
├── design/      ← authoritative current state of each module
├── proposals/   ← ideas awaiting a go/no-go decision
├── plans/       ← approved work queue (one file = one pending task)
└── archive/     ← completed plans, preserved as-is
```

`docs/` is the source of truth for project facts. `AGENTS.md` defines how to navigate and write that documentation — not the project details themselves.

---

## Design Documents (`docs/design/`)

Every core module must have a design doc. It is the authoritative reference for the module's purpose, data model, integration points, known limitations, and architectural decisions.

**What belongs in a design doc:**
- Purpose and responsibilities
- Current design (data model, read/write paths, key algorithms)
- Known limitations
- Planned or in-progress changes (link to `docs/plans/` for full specs)
- Integration points (who calls this module and how)
- Design constraints that must not be violated

---

## Proposals (`docs/proposals/`)

Ideas that are not yet approved for implementation must live here.

**Required format:**
- Title: `# Proposal: <name>`
- Metadata block: `Status`, `Created`, `Decision`, `Scope`, `Next Step`, `Related`
- `## Summary` — 3–6 lines on the idea and expected outcome
- `## Problem` — what gap or opportunity motivates it
- `## Proposal` — the actual approach
- `## Expected Value` — why this is worth attention now
- `## Risks and Open Questions` — unresolved issues that block planning
- `## Exit Criteria` — what must be true before this becomes a plan, is rejected, or is superseded

**Statuses:** `Draft` → `Review Needed` → `Approved for Plan` → `Superseded` | `Rejected`

- `Superseded` — the linked plan reached `Completed` or `Abandoned`; update when moving the plan to archive
- `Rejected` — explicitly decided against; leave in proposals/ with a decision note

**Index:** `docs/proposals/README.md` lists all active proposals (any status except `Superseded`/`Rejected`), ordered by status then newest first.

---

## Implementation Plans (`docs/plans/`)

Significant changes to existing modules or new subsystems must have a plan here before any code is written.

`docs/plans/` is a **work queue** — every file represents approved work still to be done. Do not put pre-decision ideas here. Do not leave completed plans here.

**Required metadata fields:**

```
> Status: Approved | In Progress | Completed | Abandoned
> Created: YYYY-MM-DD
> Completed: YYYY-MM-DD        ← fill when PR merges
> PR: <url>                    ← fill when PR is opened
> Proposal: <path>
```

**Plan status machine — driven by PR lifecycle:**

| Transition | Trigger | Required action |
|------------|---------|-----------------|
| `Approved` → `In Progress` | PR opened | Add `PR: <url>` to plan metadata; update Status |
| `In Progress` → `Completed` | PR merged | Add `Completed: <date>`; move file to `docs/archive/`; update linked proposal to `Superseded` |
| `In Progress` → `Abandoned` | PR closed without merge | Add `Completed: <date>` and `Abandoned Reason:`; move to `docs/archive/`; update proposal accordingly |

**Bidirectional reference rule:** every PR that implements a plan must include in its body:

```
Implements: docs/plans/<slug>.md
Proposal: docs/proposals/<slug>.md
```

This creates a traceable chain: **Proposal ↔ Plan ↔ PR**.

---

## Plan Archive (`docs/archive/`)

When a plan reaches `Completed` or `Abandoned`, move it from `docs/plans/` to `docs/archive/` with its metadata updated. Do not alter any other content.

`docs/archive/` is a read-only historical record. Design docs stay in `docs/design/` regardless of completion status — only plans move to archive.

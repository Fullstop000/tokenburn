# Agent Guide

Project-specific rules for navigating and contributing to this codebase.
For universal coding, git, and testing standards, see [CONVENTIONS.md](CONVENTIONS.md).
For project governance and documentation workflow rules, see [docs/governance.md](docs/governance.md).

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

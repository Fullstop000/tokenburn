# Project Design

> Scope: Project-level mission, invariants, repository conventions, and authoritative document map
> Last updated: 2026-03-09

## Mission

Sprout is an autonomous, self-evolving intelligence that builds deep understanding of its world, pursues goals across time, communicates with humans as partners, and deliberately improves its own capabilities.

The project is not just an automation runtime. It is an attempt to build an agent that compounds its usefulness through learning, reflection, and self-modification while remaining reviewable and controllable by humans.

## The Five Pillars

These are project-level invariants. If any one of them is violated, the system is architecturally wrong.

### 1. Autonomous Multi-Modal Operation

The agent operates continuously and chooses the highest-value use of each cycle based on its goals, knowledge, and context. It may execute tasks, discover work, study the codebase, reflect on performance, or communicate with humans. Every token spent should produce a concrete artifact: a fix, a test, an insight, a plan, a report, or a deeper understanding.

### 2. Self-Evolving Through Learning and Experience

The agent extracts learnings from both success and failure, stores them persistently, and retrieves them when relevant. It should become better over time because it remembers patterns, pitfalls, and gaps in its own understanding.

### 3. Self-Modification

The agent improves its own code through the same reviewable workflow it uses for any other code: discover a problem, plan a fix, execute, verify, and submit a PR. Its own implementation is not privileged; it is another part of the world that the agent can understand and improve.

### 4. Human-Friendly Control Plane and Observability

Humans must be able to inspect what the agent is doing, what it has done, and why. Dashboard views, logs, audit trails, and structured events are first-class product requirements rather than debugging afterthoughts.

### 5. Reviewable and Controllable Behavior

Every meaningful action should be reviewable after the fact and controllable in advance. Humans can pause, redirect, constrain, or stop the agent, and the runtime must respect those controls immediately.

## Repository Conventions

### Supported Runtime

The only supported agent runtime lives in `src/llm247_v2/`. Do not recreate `src/llm247/` or legacy startup paths without an explicit approved migration plan.

### Behavior Control

All runtime behavior configuration goes through `.llm247_v2/directive.json` or the Dashboard API. Do not hardcode behavior switches in Python code.

### Prompt Storage

Every prompt sent to the LLM must live in `src/llm247_v2/llm/prompts/*.txt` and be rendered through `prompts.render()`. Inline prompt strings in Python are not allowed.

### Git Workflow For Self-Modification

Sprout agent-created branches use the `{agent}/<task-id>-<name>` shape. All code changes go through commit, push, and PR. Force-push and direct push to `main` or `master` are blocked by `SafetyPolicy`.

### Persistence

V2 uses SQLite for structured persistence. Runtime state lives under `.llm247_v2/`, including `tasks.db`, `experience.db`, `models.db`, `directive.json`, `constitution.md`, `exploration_map.json`, `interest_profile.json`, `activity.log`, `activity.jsonl`, `llm_audit.jsonl`, and `agent.log`.

### Model Registry

Dashboard-managed model registrations and runtime binding selections live in `.llm247_v2/models.db`. LLM call sites resolve models through named `ModelBindingPoint`s instead of hardcoding one shared model.

For embeddings, registrations store the full endpoint `api_path`. For LLMs, registrations store an OpenAI-compatible `base_url`.

### Constitution Immutability

The agent must not modify `constitution.md` or `safety.py`. These paths are enforced as immutable guardrails in `constitution.py`.

### Runtime Test Naming

Maintained runtime tests use the `test_v2_*.py` prefix. Run them with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p "test_v2_*.py" -v
```

### Repository CI

The repository owns one GitHub Actions PR CI workflow in `.github/workflows/pr-ci.yml`.
It runs the maintained Python unit test suite under coverage and runs the frontend production build on pull requests to `main` and pushes to `main`.
Until the pre-existing `tests/test_v2_agent.py` failures on `main` are fixed, the backend CI command intentionally runs the stable `test_v2_*` modules except that file.

## Human Review Entry Points

The human review protocol is documented in [observability.md](observability.md). The practical entry points are:

- Liveness: `tail -f .llm247_v2/activity.log`
- Current activity: console output or Dashboard
- Task history and plans: Dashboard task views
- LLM audit trail: `.llm247_v2/llm_audit.jsonl`
- Decision traces: `.llm247_v2/activity.jsonl`

## Authoritative Docs

- [project.md](project.md) — project mission, pillars, and repository-wide conventions
- [architecture.md](architecture.md) — runtime module map, cycle, and memory stack
- [evolution.md](evolution.md) — long-range architectural roadmap
- [core.md](core.md) — models, constitution, directive, and model bindings
- [execution.md](execution.md) — planning, execution, verification, safety, git workflow
- [observability.md](observability.md) — event system, audit trail, human review protocol
- [dashboard.md](dashboard.md) — dashboard and control plane behavior

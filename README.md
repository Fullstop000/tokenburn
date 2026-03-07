# Sprout

Sprout is an autonomous, self-evolving intelligence that builds deep understanding of its world, pursues goals across time, communicates with humans as partners, and deliberately improves its own capabilities.

It is not just an automation runtime. Sprout is designed to operate continuously, produce reviewable artifacts, learn from outcomes, and improve its own implementation through the same controlled workflow it uses for any other code change.

## Core Properties

- **Autonomous multi-modal operation**: chooses the highest-value work each cycle and turns tokens into concrete artifacts
- **Learning through experience**: stores lessons from success and failure and retrieves them when relevant
- **Self-modification**: improves its own code through normal commit, push, and pull request workflows
- **Human-friendly observability**: exposes logs, audit trails, task history, and dashboard controls
- **Reviewable and controllable behavior**: humans can inspect, pause, redirect, constrain, or stop the runtime

## Current Runtime

The only supported runtime lives in `src/llm247_v2/`.

Runtime state is stored under `.llm247_v2/`, including task history, experience storage, model registry, directive state, logs, and LLM audit records.

## Architecture

Sprout is organized around seven subsystem boundaries:

- **Core**: shared models, directive, constitution, immutable rules
- **LLM**: model communication and prompt rendering
- **Storage**: SQLite-backed persistence
- **Observability**: event emission, logs, audit trail
- **Discovery**: task candidate generation and ranking
- **Execution**: planning, worktree execution, verification, git operations
- **Dashboard**: HTTP control plane and frontend

The agent cycle is:

1. Load directive and constitution
2. Discover candidate work
3. Execute the highest-value task
4. Verify and ship reviewable changes
5. Store learnings
6. Emit audit and observability events

## Documentation

Authoritative project documentation lives under [`docs/design/`](docs/design/):

- [`docs/design/project.md`](docs/design/project.md): mission, pillars, repository conventions
- [`docs/design/architecture.md`](docs/design/architecture.md): subsystem map, cycle, memory stack
- [`docs/design/core.md`](docs/design/core.md): data models, directive, constitution, model bindings
- [`docs/design/execution.md`](docs/design/execution.md): planning, execution, verification, safety, git workflow
- [`docs/design/observability.md`](docs/design/observability.md): audit trail, logs, human review protocol
- [`docs/design/evolution.md`](docs/design/evolution.md): long-range architecture roadmap

Project process and documentation rules are defined in [`AGENTS.md`](AGENTS.md).

## Quick Start

### Requirements

- Python 3.10+
- Node.js 18+ for the dashboard frontend
- Python dependencies from `requirements.txt`
- `gh` CLI if you want automated pull request creation

### Setup

```bash
cp .env.example .env
```

Model registrations and runtime bindings are managed through the Dashboard and stored in `.llm247_v2/models.db`.

### Run

```bash
./scripts/start_v2.sh agent
```

Useful variants:

```bash
./scripts/start_v2.sh ui
./scripts/start_v2.sh both
./scripts/start_v2.sh once
./scripts/start_v2.sh test
```

For maintained runtime tests, the repository convention is:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p "test_v2_*.py" -v
```

## Human Review

Useful review entry points:

- `tail -f .llm247_v2/activity.log`
- Dashboard task views and control surface
- `.llm247_v2/activity.jsonl`
- `.llm247_v2/llm_audit.jsonl`

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE).

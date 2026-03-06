# Sprout

A seed that grows into compounding engineering intelligence.

Sprout is an autonomous engineering agent that runs 24/7 — discovering what interests it in a codebase, building and verifying solutions, learning from every outcome, and evolving through experience. It starts as a simple task executor, but with every cycle it gets smarter: remembering past mistakes, forming deeper understanding of the systems it works on, and deliberately improving its own capabilities.

The agent on day 1 and the agent on day 90 are fundamentally different. The second one is better — and it made itself that way.

## What Sprout Does

|                      |                                                                                                                                                            |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Discovers**        | Scans for TODOs, test gaps, lint issues, dependency vulnerabilities, GitHub issues — and follows its own curiosity into unexplored corners of the codebase |
| **Plans & Executes** | LLM-driven planning with constitution-governed safety. All changes in isolated git worktrees.                                                              |
| **Ships**            | Commits, pushes, and creates GitHub PRs automatically. Every change is reviewable.                                                                         |
| **Learns**           | Extracts lessons from every task (success or failure), stores them persistently, and recalls relevant experience when planning future work                 |
| **Communicates**     | Dashboard control plane for real-time visibility. Help center for human-agent collaboration when the agent gets stuck.                                     |
| **Evolves**          | Improves its own source code through the same PR workflow it uses for everything else                                                                      |

## Architecture

See [docs/design/](docs/design/) for full design documentation:

- [evolution.md](docs/design/evolution.md) — Architecture roadmap: five cognitive layers
- [architecture.md](docs/design/architecture.md) — Module map, agent cycle, memory stack
- [core.md](docs/design/core.md) — Data models, constitution, directive
- [experience.md](docs/design/experience.md) — Long-term memory and learning
- [discovery.md](docs/design/discovery.md) — Task discovery strategies
- [execution.md](docs/design/execution.md) — Planning, execution, verification
- [llm.md](docs/design/llm.md) — LLM client and prompt management
- [storage.md](docs/design/storage.md) — SQLite persistence
- [observability.md](docs/design/observability.md) — Event system and audit trail
- [dashboard.md](docs/design/dashboard.md) — HTTP control plane and API

## 快速启动

### 环境要求

- Python 3.10+
- Node.js 18+（Dashboard UI 构建）
- `openai` SDK (`pip install -r requirements.txt`)
- `gh` CLI (可选，用于创建 PR)

### 配置

```bash
cp .env.example .env
# 编辑 .env，设置 ARK_API_KEY 和 ARK_MODEL
```

### 运行

```bash
# 启动 24/7 agent 循环
./scripts/start_v2.sh agent

# 仅启动 Dashboard UI
./scripts/start_v2.sh ui

# Agent + Dashboard 同时运行
./scripts/start_v2.sh both

# 运行单次循环（调试用）
./scripts/start_v2.sh once

# 运行测试
./scripts/start_v2.sh test
```

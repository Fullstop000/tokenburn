# TokenBurn: AI 自治工程代理框架

## 项目简介

TokenBurn 是一个 7x24 自治工程代理框架。它能够自主发现任务、规划执行方案、通过标准 GitHub 工作流提交变更，并提供完整的控制面进行行为管理和审查。

## V2 架构

### 核心能力

| 能力 | 说明 |
|------|------|
| **自主任务发现** | 扫描 TODO/FIXME、检测测试缺口、Lint 检查、LLM 驱动的改进发现 |
| **完整任务生命周期** | discovered → queued → planning → executing → verifying → completed/failed |
| **GitHub 工作流** | 自动创建分支、提交代码、推送并创建 PR，所有变更可 review |
| **行为控制入口** | 通过 `directive.json` 或 Dashboard API 控制 agent 行为 |
| **控制面 Dashboard** | Web UI 查看任务状态、历史、注入任务、修改配置 |
| **安全策略** | 命令白名单、路径保护、禁止 force push、自动验证 |

### 模块结构

```
src/llm247_v2/
├── models.py        # 核心数据模型 (Task, Directive, CycleReport)
├── store.py         # SQLite 持久化 (任务、事件、周期历史)
├── llm_client.py    # LLM 客户端抽象 + Ark 适配器
├── safety.py        # 命令和路径安全策略
├── discovery.py     # 任务发现引擎 (TODO/测试缺口/Lint/LLM改进)
├── planner.py       # LLM 驱动的任务执行规划
├── executor.py      # 安全动作执行器
├── git_ops.py       # Git 工作流 (分支/提交/PR)
├── verifier.py      # 执行后验证 (语法/测试/密钥检查)
├── directive.py     # Directive 行为控制系统
├── agent.py         # 主编排循环
├── dashboard.py     # HTTP 控制面 + Web UI
└── __main__.py      # CLI 入口
```

## 快速启动

### 环境要求
- Python 3.10+
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

或直接使用 Python：

```bash
# Agent 循环
PYTHONPATH=src python3 -m llm247_v2

# Dashboard
PYTHONPATH=src python3 -m llm247_v2 --ui

# 两者同时
PYTHONPATH=src python3 -m llm247_v2 --with-ui

# 单次循环
PYTHONPATH=src python3 -m llm247_v2 --once
```

Dashboard 地址: http://127.0.0.1:8787

## 行为控制 (Directive 系统)

Agent 的行为通过 `.llm247_v2/directive.json` 控制，也可以通过 Dashboard 的 Control 面板实时修改。

```json
{
  "paused": false,
  "focus_areas": ["code_quality", "testing", "documentation"],
  "forbidden_paths": [".env", ".git", "credentials.json"],
  "max_file_changes_per_task": 10,
  "custom_instructions": "优先提升测试覆盖率，避免破坏性变更",
  "task_sources": {
    "todo_scan": {"enabled": true, "priority": 2},
    "test_gap": {"enabled": true, "priority": 1},
    "lint_check": {"enabled": true, "priority": 2},
    "self_improvement": {"enabled": true, "priority": 3}
  },
  "poll_interval_seconds": 120
}
```

### Directive 字段说明

| 字段 | 作用 |
|------|------|
| `paused` | 暂停/恢复 agent |
| `focus_areas` | 引导 LLM 聚焦的领域 |
| `forbidden_paths` | 禁止修改的文件路径 |
| `max_file_changes_per_task` | 单任务最大文件变更数 |
| `custom_instructions` | 自然语言自定义指令（结构化 prompt 入口） |
| `task_sources` | 控制各任务来源的开关和优先级 |
| `poll_interval_seconds` | 循环间隔秒数 |

## Dashboard API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | Dashboard 页面 |
| `/api/tasks` | GET | 所有任务列表 |
| `/api/tasks/{id}` | GET | 任务详情 + 事件日志 |
| `/api/cycles` | GET | 周期历史 |
| `/api/stats` | GET | 统计信息 |
| `/api/directive` | GET | 当前 directive |
| `/api/directive` | POST | 更新 directive |
| `/api/tasks/inject` | POST | 手动注入任务 |
| `/api/tasks/cancel` | POST | 取消任务 |

## Agent 工作循环

每个循环执行以下步骤：

1. **加载 Directive** — 检查是否暂停，获取配置
2. **发现阶段** — 扫描 TODO、测试缺口、Lint 问题、LLM 改进建议
3. **选取任务** — 从队列中选择最高优先级任务
4. **规划阶段** — LLM 生成执行计划（文件编辑、命令、commit message、PR 描述）
5. **创建分支** — `git checkout -b agent/<task-id>-<name>`
6. **执行阶段** — 按计划执行文件操作和命令
7. **验证阶段** — 语法检查、测试运行、密钥泄露检测
8. **提交 & PR** — 提交变更、推送分支、创建 GitHub PR
9. **记录** — 所有步骤写入 SQLite 审计日志

## 安全机制

- **命令白名单**: 仅允许安全的系统命令
- **Git 保护**: 禁止 force push、禁止直接推送 main/master、禁止 --no-verify
- **路径保护**: `.env`、`.git`、敏感文件不可修改
- **路径遍历防护**: 文件操作限制在 workspace 内
- **文件大小限制**: 单文件 200KB 上限
- **执行后验证**: 语法、测试、密钥泄露自动检查

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `ARK_API_KEY` | 是 | - | LLM API Key |
| `ARK_MODEL` | 是 | - | 模型标识 |
| `ARK_BASE_URL` | 否 | Ark Beijing | API 端点 |
| `WORKSPACE_PATH` | 否 | 当前目录 | 工作区路径 |
| `POLL_INTERVAL_SECONDS` | 否 | 120 | 循环间隔 |
| `COMMAND_TIMEOUT_SECONDS` | 否 | 60 | 命令超时 |

## 贡献指南

提交信息遵循 Conventional Commits：
- `feat(scope): 添加新功能`
- `fix(scope): 修复 BUG`
- `refactor(scope): 代码重构`
- `test(scope): 测试变更`
- `docs(scope): 文档更新`

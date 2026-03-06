# llm247_v2 模块化重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `src/llm247_v2/` 下的 18 个平铺文件按职责拆分到 6 个子模块目录，提升可读性与可扩展性，同时同步更新全部 imports（含测试）。

**Architecture:** 按"依赖层级"由低到高划分模块：`core/`（基础模型）→ `llm/`（LLM 客户端+Prompts）→ `storage/`（持久化）→ `observability/`（观测）→ `discovery/`（发现管道）→ `execution/`（执行管道）→ `dashboard/`（控制面板），`agent.py` 和 `__main__.py` 留在根目录作为入口编排层。

**Tech Stack:** Python 3.10+, SQLite, stdlib only (no external refactoring tools)

---

## 目标目录结构

```
src/llm247_v2/
├── __init__.py              # 保持包入口，可选添加便利 re-export
├── __main__.py              # CLI 入口（只更新 imports）
├── agent.py                 # 主编排器（只更新 imports）
│
├── core/                    # 共享基础层（无内部依赖）
│   ├── __init__.py
│   ├── models.py            # ← 原 models.py
│   ├── constitution.py      # ← 原 constitution.py
│   └── directive.py         # ← 原 directive.py
│
├── llm/                     # LLM 客户端 + Prompt 模板
│   ├── __init__.py
│   ├── client.py            # ← 原 llm_client.py（改名）
│   └── prompts/             # ← 原 prompts/（整体移动）
│       ├── __init__.py
│       ├── plan_task.txt
│       ├── assess_value.txt
│       ├── extract_learnings.txt
│       ├── discover_stale_area.txt
│       ├── discover_deep_review.txt
│       ├── discover_llm_guided.txt
│       └── discover_web_search.txt
│
├── storage/                 # 数据持久化层
│   ├── __init__.py
│   ├── store.py             # ← 原 store.py
│   └── experience.py        # ← 原 experience.py
│
├── observability/           # 事件观测层
│   ├── __init__.py
│   └── observer.py          # ← 原 observer.py
│
├── discovery/               # 任务发现管道
│   ├── __init__.py
│   ├── pipeline.py          # ← 原 discovery.py（改名避免与包名冲突）
│   ├── exploration.py       # ← 原 exploration.py
│   ├── value.py             # ← 原 value.py
│   └── interest.py          # ← 原 interest.py
│
├── execution/               # 任务执行管道
│   ├── __init__.py
│   ├── planner.py           # ← 原 planner.py
│   ├── executor.py          # ← 原 executor.py
│   ├── verifier.py          # ← 原 verifier.py
│   ├── git_ops.py           # ← 原 git_ops.py
│   └── safety.py            # ← 原 safety.py
│
└── dashboard/               # HTTP 控制面板
    ├── __init__.py
    └── server.py            # ← 原 dashboard.py（改名）
```

---

## Import 映射表（旧 → 新）

| 旧路径 | 新路径 |
|--------|--------|
| `llm247_v2.models` | `llm247_v2.core.models` |
| `llm247_v2.constitution` | `llm247_v2.core.constitution` |
| `llm247_v2.directive` | `llm247_v2.core.directive` |
| `llm247_v2.llm_client` | `llm247_v2.llm.client` |
| `llm247_v2.prompts` | `llm247_v2.llm.prompts` |
| `llm247_v2.store` | `llm247_v2.storage.store` |
| `llm247_v2.experience` | `llm247_v2.storage.experience` |
| `llm247_v2.observer` | `llm247_v2.observability.observer` |
| `llm247_v2.discovery` | `llm247_v2.discovery.pipeline` |
| `llm247_v2.exploration` | `llm247_v2.discovery.exploration` |
| `llm247_v2.value` | `llm247_v2.discovery.value` |
| `llm247_v2.interest` | `llm247_v2.discovery.interest` |
| `llm247_v2.planner` | `llm247_v2.execution.planner` |
| `llm247_v2.executor` | `llm247_v2.execution.executor` |
| `llm247_v2.verifier` | `llm247_v2.execution.verifier` |
| `llm247_v2.git_ops` | `llm247_v2.execution.git_ops` |
| `llm247_v2.safety` | `llm247_v2.execution.safety` |
| `llm247_v2.dashboard` | `llm247_v2.dashboard.server` |

---

## Task 1: 创建子模块目录骨架

**Files:**
- Create: `src/llm247_v2/core/__init__.py`
- Create: `src/llm247_v2/llm/__init__.py`
- Create: `src/llm247_v2/storage/__init__.py`
- Create: `src/llm247_v2/observability/__init__.py`
- Create: `src/llm247_v2/discovery/__init__.py`
- Create: `src/llm247_v2/execution/__init__.py`
- Create: `src/llm247_v2/dashboard/__init__.py`

**Step 1:** 创建所有子模块目录和空 `__init__.py`

```bash
mkdir -p src/llm247_v2/{core,llm,storage,observability,discovery,execution,dashboard}
for d in core llm storage observability discovery execution dashboard; do
  touch src/llm247_v2/$d/__init__.py
done
```

**Step 2:** 验证目录结构

```bash
find src/llm247_v2 -name "__init__.py" | sort
```
Expected: 看到 8 个 `__init__.py`（根+7个子目录）

**Step 3:** Commit

```bash
git add src/llm247_v2/
git commit -m "chore(llm247_v2): scaffold submodule directories"
```

---

## Task 2: 迁移 core/ 层（models, constitution, directive）

**Files:**
- Move: `src/llm247_v2/models.py` → `src/llm247_v2/core/models.py`
- Move: `src/llm247_v2/constitution.py` → `src/llm247_v2/core/constitution.py`
- Move: `src/llm247_v2/directive.py` → `src/llm247_v2/core/directive.py`

**Step 1:** 移动文件

```bash
git mv src/llm247_v2/models.py src/llm247_v2/core/models.py
git mv src/llm247_v2/constitution.py src/llm247_v2/core/constitution.py
git mv src/llm247_v2/directive.py src/llm247_v2/core/directive.py
```

**Step 2:** 更新 `core/directive.py` 内部 import（旧→新）

```python
# 旧
from llm247_v2.models import Directive, TaskSourceConfig
# 新
from llm247_v2.core.models import Directive, TaskSourceConfig
```

**Step 3:** 写入 `core/__init__.py` re-export（便利访问）

```python
"""llm247_v2.core — shared data models, constitution, and directive."""
from llm247_v2.core.models import (
    CycleReport, Directive, PlanStep, Task, TaskPlan,
    TaskSource, TaskSourceConfig, TaskStatus,
)
from llm247_v2.core.constitution import Constitution, load_constitution
from llm247_v2.core.directive import (
    default_directive, directive_to_prompt_section,
    load_directive, save_directive,
)

__all__ = [
    "CycleReport", "Directive", "PlanStep", "Task", "TaskPlan",
    "TaskSource", "TaskSourceConfig", "TaskStatus",
    "Constitution", "load_constitution",
    "default_directive", "directive_to_prompt_section",
    "load_directive", "save_directive",
]
```

**Step 4:** 运行迁移后的 core 测试

```bash
PYTHONPATH=src python -m pytest tests/test_v2_models.py tests/test_v2_constitution.py tests/test_v2_directive.py -v --no-header 2>&1 | head -40
```
Expected: 此阶段会 **FAIL**（其他模块 import 旧路径）——记录错误，继续下一个 Task

**Step 5:** Commit

```bash
git add src/llm247_v2/core/
git commit -m "refactor(llm247_v2): move core layer to core/ submodule"
```

---

## Task 3: 迁移 llm/ 层（llm_client → client, prompts 整体移动）

**Files:**
- Move: `src/llm247_v2/llm_client.py` → `src/llm247_v2/llm/client.py`
- Move: `src/llm247_v2/prompts/` → `src/llm247_v2/llm/prompts/`（整体）

**Step 1:** 移动 llm_client

```bash
git mv src/llm247_v2/llm_client.py src/llm247_v2/llm/client.py
```

**Step 2:** 移动 prompts 目录

```bash
git mv src/llm247_v2/prompts src/llm247_v2/llm/prompts
```

**Step 3:** 更新 `llm/prompts/__init__.py` 中的路径查找逻辑

打开 `src/llm247_v2/llm/prompts/__init__.py`，找到读取 `.txt` 文件的路径，确认用 `Path(__file__).parent` 来定位模板目录（通常已是相对路径，不需改）。

**Step 4:** 写入 `llm/__init__.py`

```python
"""llm247_v2.llm — LLM client, token tracking, audit logging, and prompt templates."""
from llm247_v2.llm.client import (
    ArkLLMClient, BudgetExhaustedError, LLMAuditLogger,
    LLMClient, TokenTracker, UsageInfo, extract_json,
)
from llm247_v2.llm.prompts import render

__all__ = [
    "ArkLLMClient", "BudgetExhaustedError", "LLMAuditLogger",
    "LLMClient", "TokenTracker", "UsageInfo", "extract_json",
    "render",
]
```

**Step 5:** 运行 llm 相关测试

```bash
PYTHONPATH=src python -m pytest tests/test_v2_llm_client.py tests/test_v2_prompts.py -v --no-header 2>&1 | head -40
```

**Step 6:** Commit

```bash
git add src/llm247_v2/llm/
git commit -m "refactor(llm247_v2): move LLM client and prompts to llm/ submodule"
```

---

## Task 4: 迁移 storage/ 层（store, experience）

**Files:**
- Move: `src/llm247_v2/store.py` → `src/llm247_v2/storage/store.py`
- Move: `src/llm247_v2/experience.py` → `src/llm247_v2/storage/experience.py`

**Step 1:** 移动文件

```bash
git mv src/llm247_v2/store.py src/llm247_v2/storage/store.py
git mv src/llm247_v2/experience.py src/llm247_v2/storage/experience.py
```

**Step 2:** 更新 `storage/store.py` 内部 imports

```python
# 旧
from llm247_v2.models import CycleReport, Task
# 新
from llm247_v2.core.models import CycleReport, Task
```

**Step 3:** 更新 `storage/experience.py` 内部 imports

```python
# 旧
from llm247_v2.prompts import render as render_prompt
# 新
from llm247_v2.llm.prompts import render as render_prompt
```

**Step 4:** 写入 `storage/__init__.py`

```python
"""llm247_v2.storage — SQLite persistence for tasks, cycles, and experience."""
from llm247_v2.storage.store import TaskStore
from llm247_v2.storage.experience import ExperienceStore, extract_learnings, format_experiences_for_prompt, format_whats_learned

__all__ = [
    "TaskStore",
    "ExperienceStore", "extract_learnings",
    "format_experiences_for_prompt", "format_whats_learned",
]
```

**Step 5:** Commit

```bash
git add src/llm247_v2/storage/
git commit -m "refactor(llm247_v2): move persistence layer to storage/ submodule"
```

---

## Task 5: 迁移 observability/ 层（observer）

**Files:**
- Move: `src/llm247_v2/observer.py` → `src/llm247_v2/observability/observer.py`

**Step 1:** 移动文件

```bash
git mv src/llm247_v2/observer.py src/llm247_v2/observability/observer.py
```

**Step 2:** 检查并更新 observer 内部 imports（如有引用 store/models）

打开文件，若有 `from llm247_v2.store` 则改为 `from llm247_v2.storage.store`。

**Step 3:** 写入 `observability/__init__.py`

```python
"""llm247_v2.observability — centralized event emission and multi-handler routing."""
from llm247_v2.observability.observer import (
    AgentEvent, ConsoleHandler, HumanLogHandler,
    JsonLogHandler, MemoryHandler, NullObserver,
    Observer, StoreHandler, create_default_observer,
)

__all__ = [
    "AgentEvent", "ConsoleHandler", "HumanLogHandler",
    "JsonLogHandler", "MemoryHandler", "NullObserver",
    "Observer", "StoreHandler", "create_default_observer",
]
```

**Step 4:** Commit

```bash
git add src/llm247_v2/observability/
git commit -m "refactor(llm247_v2): move observability layer to observability/ submodule"
```

---

## Task 6: 迁移 execution/ 层（safety, planner, executor, verifier, git_ops）

**Files:**
- Move: `src/llm247_v2/safety.py` → `src/llm247_v2/execution/safety.py`
- Move: `src/llm247_v2/planner.py` → `src/llm247_v2/execution/planner.py`
- Move: `src/llm247_v2/executor.py` → `src/llm247_v2/execution/executor.py`
- Move: `src/llm247_v2/verifier.py` → `src/llm247_v2/execution/verifier.py`
- Move: `src/llm247_v2/git_ops.py` → `src/llm247_v2/execution/git_ops.py`

**Step 1:** 移动文件

```bash
git mv src/llm247_v2/safety.py src/llm247_v2/execution/safety.py
git mv src/llm247_v2/planner.py src/llm247_v2/execution/planner.py
git mv src/llm247_v2/executor.py src/llm247_v2/execution/executor.py
git mv src/llm247_v2/verifier.py src/llm247_v2/execution/verifier.py
git mv src/llm247_v2/git_ops.py src/llm247_v2/execution/git_ops.py
```

**Step 2:** 更新 `execution/executor.py` imports

```python
# 旧
from llm247_v2.models import Directive, PlanStep, TaskPlan
from llm247_v2.safety import SafetyPolicy
# 新
from llm247_v2.core.models import Directive, PlanStep, TaskPlan
from llm247_v2.execution.safety import SafetyPolicy
```

**Step 3:** 更新 `execution/planner.py` imports

```python
# 旧
from llm247_v2.constitution import Constitution
from llm247_v2.directive import directive_to_prompt_section
from llm247_v2.llm_client import LLMClient, extract_json
from llm247_v2.models import Directive, PlanStep, Task, TaskPlan
from llm247_v2.prompts import render as render_prompt
# 新
from llm247_v2.core.constitution import Constitution
from llm247_v2.core.directive import directive_to_prompt_section
from llm247_v2.llm.client import LLMClient, extract_json
from llm247_v2.core.models import Directive, PlanStep, Task, TaskPlan
from llm247_v2.llm.prompts import render as render_prompt
```

以及 `planner.py` 中 lazy import：
```python
# 旧（在函数内）
from llm247_v2.constitution import _default_constitution
# 新
from llm247_v2.core.constitution import _default_constitution
```

**Step 4:** 写入 `execution/__init__.py`

```python
"""llm247_v2.execution — task planning, safe execution, verification, and git workflow."""
from llm247_v2.execution.safety import SafetyPolicy
from llm247_v2.execution.planner import deserialize_plan, plan_task_with_constitution, serialize_plan
from llm247_v2.execution.executor import PlanExecutor, format_execution_log
from llm247_v2.execution.verifier import format_verification, verify_task
from llm247_v2.execution.git_ops import GitOperationError, GitWorkflow

__all__ = [
    "SafetyPolicy",
    "deserialize_plan", "plan_task_with_constitution", "serialize_plan",
    "PlanExecutor", "format_execution_log",
    "format_verification", "verify_task",
    "GitOperationError", "GitWorkflow",
]
```

**Step 5:** Commit

```bash
git add src/llm247_v2/execution/
git commit -m "refactor(llm247_v2): move execution pipeline to execution/ submodule"
```

---

## Task 7: 迁移 discovery/ 层（discovery → pipeline, exploration, value, interest）

**Files:**
- Move: `src/llm247_v2/discovery.py` → `src/llm247_v2/discovery/pipeline.py`
- Move: `src/llm247_v2/exploration.py` → `src/llm247_v2/discovery/exploration.py`
- Move: `src/llm247_v2/value.py` → `src/llm247_v2/discovery/value.py`
- Move: `src/llm247_v2/interest.py` → `src/llm247_v2/discovery/interest.py`

**Step 1:** 移动文件

```bash
git mv src/llm247_v2/exploration.py src/llm247_v2/discovery/exploration.py
git mv src/llm247_v2/value.py src/llm247_v2/discovery/value.py
git mv src/llm247_v2/interest.py src/llm247_v2/discovery/interest.py
git mv src/llm247_v2/discovery.py src/llm247_v2/discovery/pipeline.py
```

**Step 2:** 更新 `discovery/exploration.py` imports

```python
# 旧
from llm247_v2.constitution import Constitution
from llm247_v2.llm_client import LLMClient, extract_json
from llm247_v2.models import Directive
# 新
from llm247_v2.core.constitution import Constitution
from llm247_v2.llm.client import LLMClient, extract_json
from llm247_v2.core.models import Directive
```

**Step 3:** 更新 `discovery/value.py` imports

```python
# 旧
from llm247_v2.constitution import Constitution
from llm247_v2.llm_client import LLMClient, extract_json
from llm247_v2.models import Directive, Task
from llm247_v2.prompts import render as render_prompt
# 新
from llm247_v2.core.constitution import Constitution
from llm247_v2.llm.client import LLMClient, extract_json
from llm247_v2.core.models import Directive, Task
from llm247_v2.llm.prompts import render as render_prompt
```

**Step 4:** 更新 `discovery/interest.py` imports

```python
# 旧（包括 lazy imports）
from llm247_v2.models import Directive, Task, TaskSource, TaskStatus
from llm247_v2.prompts import render as render_prompt
# 在函数内 lazy:
from llm247_v2.experience import ExperienceStore
from llm247_v2.exploration import ExplorationMap
from llm247_v2.llm_client import extract_json
from llm247_v2.llm_client import LLMClient
# 新
from llm247_v2.core.models import Directive, Task, TaskSource, TaskStatus
from llm247_v2.llm.prompts import render as render_prompt
# lazy:
from llm247_v2.storage.experience import ExperienceStore
from llm247_v2.discovery.exploration import ExplorationMap
from llm247_v2.llm.client import extract_json
from llm247_v2.llm.client import LLMClient
```

**Step 5:** 更新 `discovery/pipeline.py` imports

```python
# 旧
from llm247_v2.constitution import Constitution
from llm247_v2.prompts import render as render_prompt
from llm247_v2.exploration import (ExplorationMap, Strategy, ...)
from llm247_v2.interest import (...)
from llm247_v2.llm_client import LLMClient, extract_json
from llm247_v2.models import Directive, Task, TaskSource, TaskStatus
from llm247_v2.value import (...)
# lazy:
from llm247_v2.observer import Observer
# 新
from llm247_v2.core.constitution import Constitution
from llm247_v2.llm.prompts import render as render_prompt
from llm247_v2.discovery.exploration import (ExplorationMap, Strategy, ...)
from llm247_v2.discovery.interest import (...)
from llm247_v2.llm.client import LLMClient, extract_json
from llm247_v2.core.models import Directive, Task, TaskSource, TaskStatus
from llm247_v2.discovery.value import (...)
# lazy:
from llm247_v2.observability.observer import Observer
```

**Step 6:** 写入 `discovery/__init__.py`

```python
"""llm247_v2.discovery — task discovery pipeline, exploration map, value assessment, and interest profiling."""
from llm247_v2.discovery.pipeline import discover_and_evaluate
from llm247_v2.discovery.exploration import (
    ExplorationMap, Strategy,
    build_deep_review_context, load_exploration_map,
    record_strategy_result, save_exploration_map,
    scan_change_hotspots, scan_complexity,
    scan_stale_areas, select_strategy,
)
from llm247_v2.discovery.value import assess_task_value
from llm247_v2.discovery.interest import Interest, InterestProfile

__all__ = [
    "discover_and_evaluate",
    "ExplorationMap", "Strategy",
    "build_deep_review_context", "load_exploration_map",
    "record_strategy_result", "save_exploration_map",
    "scan_change_hotspots", "scan_complexity",
    "scan_stale_areas", "select_strategy",
    "assess_task_value",
    "Interest", "InterestProfile",
]
```

**Step 7:** Commit

```bash
git add src/llm247_v2/discovery/
git commit -m "refactor(llm247_v2): move discovery pipeline to discovery/ submodule"
```

---

## Task 8: 迁移 dashboard/ 层（dashboard → server）

**Files:**
- Move: `src/llm247_v2/dashboard.py` → `src/llm247_v2/dashboard/server.py`

**Step 1:** 移动文件

```bash
git mv src/llm247_v2/dashboard.py src/llm247_v2/dashboard/server.py
```

**Step 2:** 更新 `dashboard/server.py` imports

```python
# 旧
from llm247_v2.directive import load_directive, save_directive
from llm247_v2.models import Directive, TaskSourceConfig, TaskStatus
from llm247_v2.store import TaskStore
# lazy:
from llm247_v2.models import Task, TaskSource
# 新
from llm247_v2.core.directive import load_directive, save_directive
from llm247_v2.core.models import Directive, TaskSourceConfig, TaskStatus
from llm247_v2.storage.store import TaskStore
# lazy:
from llm247_v2.core.models import Task, TaskSource
```

**Step 3:** 写入 `dashboard/__init__.py`

```python
"""llm247_v2.dashboard — HTTP control plane and web UI server."""
from llm247_v2.dashboard.server import serve_dashboard

__all__ = ["serve_dashboard"]
```

**Step 4:** Commit

```bash
git add src/llm247_v2/dashboard/
git commit -m "refactor(llm247_v2): move dashboard server to dashboard/ submodule"
```

---

## Task 9: 更新根入口文件（agent.py, __main__.py）

**Files:**
- Modify: `src/llm247_v2/agent.py`
- Modify: `src/llm247_v2/__main__.py`

**Step 1:** 更新 `agent.py` 所有 imports（按 Import 映射表批量替换）

完整新 imports 示例：
```python
from llm247_v2.core.constitution import Constitution, load_constitution
from llm247_v2.core.directive import load_directive
from llm247_v2.discovery.pipeline import discover_and_evaluate
from llm247_v2.execution.executor import PlanExecutor, format_execution_log
from llm247_v2.storage.experience import (
    ExperienceStore, extract_learnings,
    format_experiences_for_prompt, format_whats_learned,
)
from llm247_v2.discovery.exploration import load_exploration_map, save_exploration_map
from llm247_v2.execution.git_ops import GitOperationError, GitWorkflow
from llm247_v2.discovery.interest import (
    Interest, InterestProfile, build_interest_profile,
)
from llm247_v2.llm.client import BudgetExhaustedError, LLMClient, TokenTracker, extract_json
from llm247_v2.core.models import Directive, TaskStatus
from llm247_v2.observability.observer import NullObserver, Observer
from llm247_v2.execution.planner import plan_task_with_constitution, serialize_plan
from llm247_v2.execution.safety import SafetyPolicy
from llm247_v2.storage.store import TaskStore
from llm247_v2.execution.verifier import format_verification, verify_task
# lazy import in method:
from llm247_v2.discovery.interest import Interest
```

**Step 2:** 更新 `__main__.py` imports

```python
from llm247_v2.dashboard.server import serve_dashboard
from llm247_v2.agent import AutonomousAgentV2, GracefulShutdown, run_agent_loop
from llm247_v2.storage.experience import ExperienceStore
from llm247_v2.llm.client import ArkLLMClient, BudgetExhaustedError, LLMAuditLogger
from llm247_v2.observability.observer import create_default_observer
from llm247_v2.storage.store import TaskStore
```

**Step 3:** Commit

```bash
git add src/llm247_v2/agent.py src/llm247_v2/__main__.py
git commit -m "refactor(llm247_v2): update root entry files to use new submodule imports"
```

---

## Task 10: 更新测试文件中的所有 imports

**Files:**
- Modify: `tests/test_v2_*.py`（共 17 个测试文件）

**参考映射，批量替换：**

```
tests/test_v2_models.py       : llm247_v2.models → llm247_v2.core.models
tests/test_v2_constitution.py : llm247_v2.constitution → llm247_v2.core.constitution
tests/test_v2_directive.py    : llm247_v2.directive → llm247_v2.core.directive
                                 llm247_v2.models → llm247_v2.core.models
tests/test_v2_llm_client.py   : llm247_v2.llm_client → llm247_v2.llm.client
tests/test_v2_prompts.py      : llm247_v2.prompts → llm247_v2.llm.prompts
tests/test_v2_store.py        : llm247_v2.store → llm247_v2.storage.store
                                 llm247_v2.models → llm247_v2.core.models
tests/test_v2_experience.py   : llm247_v2.experience → llm247_v2.storage.experience
                                 llm247_v2.llm_client → llm247_v2.llm.client
tests/test_v2_observer.py     : llm247_v2.observer → llm247_v2.observability.observer
tests/test_v2_safety.py       : llm247_v2.safety → llm247_v2.execution.safety
tests/test_v2_executor.py     : llm247_v2.executor → llm247_v2.execution.executor
                                 llm247_v2.models → llm247_v2.core.models
                                 llm247_v2.safety → llm247_v2.execution.safety
tests/test_v2_verifier.py     : llm247_v2.verifier → llm247_v2.execution.verifier
tests/test_v2_git_ops.py      : llm247_v2.git_ops → llm247_v2.execution.git_ops
tests/test_v2_planner.py      : llm247_v2.planner → llm247_v2.execution.planner
                                 llm247_v2.models → llm247_v2.core.models
tests/test_v2_value.py        : llm247_v2.value → llm247_v2.discovery.value
                                 llm247_v2.models → llm247_v2.core.models
tests/test_v2_exploration.py  : llm247_v2.exploration → llm247_v2.discovery.exploration
                                 llm247_v2.constitution → llm247_v2.core.constitution
                                 llm247_v2.models → llm247_v2.core.models
tests/test_v2_interest.py     : llm247_v2.interest → llm247_v2.discovery.interest
                                 llm247_v2.models → llm247_v2.core.models
tests/test_v2_discovery.py    : llm247_v2.discovery → llm247_v2.discovery.pipeline
                                 llm247_v2.constitution → llm247_v2.core.constitution
                                 llm247_v2.exploration → llm247_v2.discovery.exploration
                                 llm247_v2.models → llm247_v2.core.models
tests/test_v2_dashboard.py    : llm247_v2.dashboard → llm247_v2.dashboard.server
                                 llm247_v2.directive → llm247_v2.core.directive
                                 llm247_v2.models → llm247_v2.core.models
                                 llm247_v2.store → llm247_v2.storage.store
tests/test_v2_agent.py        : llm247_v2.agent → (不变)
                                 llm247_v2.directive → llm247_v2.core.directive
                                 llm247_v2.llm_client → llm247_v2.llm.client
                                 llm247_v2.models → llm247_v2.core.models
                                 llm247_v2.observer → llm247_v2.observability.observer
                                 llm247_v2.store → llm247_v2.storage.store
```

**Step 1:** 运行全量 V2 测试，记录基线

```bash
PYTHONPATH=src python -m pytest tests/test_v2_*.py --tb=no -q 2>&1 | tail -5
```

**Step 2:** 更新所有测试文件（逐个或批量 sed）

```bash
# 示例：批量替换（在 tests/ 目录运行）
sed -i '' 's/from llm247_v2\.models /from llm247_v2.core.models /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.constitution /from llm247_v2.core.constitution /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.directive /from llm247_v2.core.directive /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.llm_client /from llm247_v2.llm.client /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.prompts /from llm247_v2.llm.prompts /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.store /from llm247_v2.storage.store /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.experience /from llm247_v2.storage.experience /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.observer /from llm247_v2.observability.observer /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.safety /from llm247_v2.execution.safety /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.executor /from llm247_v2.execution.executor /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.verifier /from llm247_v2.execution.verifier /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.git_ops /from llm247_v2.execution.git_ops /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.planner /from llm247_v2.execution.planner /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.value /from llm247_v2.discovery.value /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.exploration /from llm247_v2.discovery.exploration /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.interest /from llm247_v2.discovery.interest /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.discovery /from llm247_v2.discovery.pipeline /g' tests/test_v2_*.py
sed -i '' 's/from llm247_v2\.dashboard /from llm247_v2.dashboard.server /g' tests/test_v2_*.py
```

**Step 3:** 运行全量 V2 测试，对比基线

```bash
PYTHONPATH=src python -m pytest tests/test_v2_*.py -v --tb=short 2>&1 | tail -30
```
Expected: 所有原本通过的测试仍然通过，无新的失败

**Step 4:** Commit

```bash
git add tests/test_v2_*.py
git commit -m "refactor(llm247_v2): update test imports to new submodule paths"
```

---

## Task 11: 更新根 __init__.py + AGENTS.md 模块图

**Files:**
- Modify: `src/llm247_v2/__init__.py`
- Modify: `AGENTS.md`

**Step 1:** 更新根 `__init__.py`，添加包说明和版本

```python
"""llm247_v2: Autonomous 24/7 engineering agent with full task lifecycle and GitHub workflow.

Submodule layout:
  core/          — data models, constitution, directive
  llm/           — LLM client, token tracking, audit logging, prompt templates
  storage/       — SQLite persistence (tasks, cycles, experiences)
  observability/ — centralized event emission and routing
  discovery/     — task discovery pipeline, exploration, value assessment, interest
  execution/     — planning, safe execution, verification, git workflow, safety policy
  dashboard/     — HTTP control plane and web UI
"""
```

**Step 2:** 更新 AGENTS.md 中的 "Module Map" 部分，替换为新的目录结构

**Step 3:** 最终全量测试

```bash
PYTHONPATH=src python -m pytest tests/test_v2_*.py -v --tb=short 2>&1 | tail -20
```
Expected: 全部绿灯

**Step 4:** 最终 Commit

```bash
git add src/llm247_v2/__init__.py AGENTS.md
git commit -m "docs(llm247_v2): update module map in __init__.py and AGENTS.md"
```

---

## 风险 & 注意事项

1. **`discovery.py` → `pipeline.py` 改名：** 原文件名与子目录名冲突，必须改名。所有引用 `discover_and_evaluate` 等函数的地方需改为 `from llm247_v2.discovery.pipeline import ...`。

2. **`dashboard.py` → `server.py` 改名：** `test_v2_dashboard.py` 中直接 import 了多个私有函数（`_api_tasks`, `_task_row` 等），这些名字不变，只有模块路径变。

3. **`llm_client.py` → `llm/client.py` 改名：** 注意 `LLMAuditLogger` 写文件路径时使用 `Path(__file__)` 的情况——路径改变不影响功能，但要确认。

4. **`prompts/__init__.py` 中的文件路径：** `render()` 函数使用 `Path(__file__).parent` 查找 `.txt` 模板文件，移动整个目录后不受影响。

5. **`constitution.py` 中的 `IMMUTABLE_PATHS`：** 包含 `"safety.py"` 路径，这是文件名检测，不受模块路径变化影响。

6. **`experience.py` 中的 lazy imports：** 使用 `TYPE_CHECKING` 或函数内 import 的地方，均需更新。

7. **执行顺序很重要：** 必须按 Task 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 顺序执行，因为高层模块依赖低层模块的新路径。

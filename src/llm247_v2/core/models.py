from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class TaskStatus(str, Enum):
    DISCOVERED = "discovered"
    QUEUED = "queued"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    NEEDS_HUMAN = "needs_human"
    HUMAN_RESOLVED = "human_resolved"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskSource(str, Enum):
    TODO_SCAN = "todo_scan"
    LINT_CHECK = "lint_check"
    TEST_GAP = "test_gap"
    SELF_IMPROVEMENT = "self_improvement"
    MANUAL = "manual"
    BACKLOG = "backlog"
    GITHUB_ISSUE = "github_issue"
    DEP_AUDIT = "dep_audit"
    WEB_SEARCH = "web_search"
    INTEREST_DRIVEN = "interest_driven"


class ModelType(str, Enum):
    """Supported registered model families."""

    EMBEDDING = "embedding"
    LLM = "llm"


class ModelBindingPoint(str, Enum):
    """Named runtime call sites that can be bound to registered models."""

    EXECUTION = "execution"
    TASK_VALUE = "task_value"
    DISCOVERY_GENERATION = "discovery_generation"
    INTEREST_DRIVEN_DISCOVERY = "interest_driven_discovery"
    WEB_SEARCH_DISCOVERY = "web_search_discovery"
    LEARNING_EXTRACTION = "learning_extraction"
    EXPERIENCE_MERGE = "experience_merge"


@dataclass
class Task:
    """One unit of work tracked across discovery, execution, and human handoff."""

    id: str
    title: str
    description: str
    source: str
    status: str = TaskStatus.DISCOVERED.value
    priority: int = 3
    created_at: str = ""
    updated_at: str = ""
    branch_name: str = ""
    pr_url: str = ""
    execution_trace: str = ""
    execution_log: str = ""
    error_message: str = ""
    cycle_id: int = 0
    prompt_token_cost: int = 0
    completion_token_cost: int = 0
    token_cost: int = 0
    time_cost_seconds: float = 0.0
    whats_learned: str = ""
    human_help_request: str = ""



@dataclass
class RegisteredModel:
    """One persisted model registration available to the dashboard and runtime."""

    id: str
    model_type: str
    model_name: str
    api_key: str
    base_url: str = ""
    api_path: str = ""
    desc: str = ""
    roocode_wrapper: bool = False
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ModelBinding:
    """Binds one runtime call site to a registered model id."""

    binding_point: str
    model_id: str
    updated_at: str = ""


@dataclass(frozen=True)
class ModelBindingSpec:
    """Static metadata describing one configurable runtime binding point."""

    binding_point: str
    label: str
    description: str
    model_type: str


@dataclass
class ToolCall:
    tool: str
    arguments: dict
    reasoning: str = ""


@dataclass
class ToolResult:
    tool: str
    arguments: dict
    success: bool
    output: str


@dataclass
class CycleReport:
    cycle_id: int
    started_at: str
    completed_at: str = ""
    tasks_discovered: int = 0
    tasks_executed: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    status: str = "running"
    summary: str = ""


@dataclass
class TaskSourceConfig:
    enabled: bool = True
    priority: int = 3


@dataclass
class Directive:
    paused: bool = False
    focus_areas: List[str] = field(default_factory=list)
    forbidden_paths: List[str] = field(default_factory=list)
    max_file_changes_per_task: int = 10
    custom_instructions: str = ""
    task_sources: Dict[str, TaskSourceConfig] = field(default_factory=dict)
    poll_interval_seconds: int = 120
    max_steps: int = 50
    max_tokens_per_task: int = 0

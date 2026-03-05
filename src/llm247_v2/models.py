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


@dataclass
class Task:
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
    plan: str = ""
    execution_log: str = ""
    verification_result: str = ""
    error_message: str = ""
    cycle_id: int = 0
    token_cost: int = 0
    time_cost_seconds: float = 0.0
    whats_learned: str = ""


@dataclass
class PlanStep:
    action: str
    target: str
    content: str = ""
    description: str = ""


@dataclass
class TaskPlan:
    task_id: str
    steps: List[PlanStep] = field(default_factory=list)
    commit_message: str = ""
    pr_title: str = ""
    pr_body: str = ""


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

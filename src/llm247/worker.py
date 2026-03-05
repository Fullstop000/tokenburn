from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Protocol

from llm247.reports import ReportWriter
from llm247.scheduler import is_task_due
from llm247.storage import TaskStateStore


@dataclass(frozen=True)
class TaskContext:
    """Runtime context passed into task prompt builders."""

    workspace_path: Path
    report_dir: Path
    now: datetime


@dataclass(frozen=True)
class WorkerTask:
    """A periodic LLM task with fixed execution interval."""

    name: str
    interval_seconds: int
    prompt_builder: Callable[[TaskContext], str]

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than 0")


class ModelClient(Protocol):
    """Protocol for text generation clients used by the worker."""

    def generate_text(self, prompt: str) -> str:
        """Generate text output from one user prompt."""


class ContinuousWorker:
    """Execute periodic LLM tasks continuously with durable run state."""

    def __init__(
        self,
        workspace_path: Path,
        state_store: TaskStateStore,
        report_writer: ReportWriter,
        model_client: ModelClient,
        tasks: List[WorkerTask],
    ) -> None:
        if not tasks:
            raise ValueError("at least one task is required")

        self.workspace_path = workspace_path
        self.state_store = state_store
        self.report_writer = report_writer
        self.model_client = model_client
        self.tasks = tasks
        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            self.logger.addHandler(logging.NullHandler())

    def run_once(self, now: datetime | None = None) -> List[Path]:
        """Run all due tasks once and return generated report file paths."""
        run_at = now or datetime.now(timezone.utc)
        context = TaskContext(
            workspace_path=self.workspace_path,
            report_dir=self.report_writer.report_dir,
            now=run_at,
        )

        generated_reports: List[Path] = []
        for task in self.tasks:
            try:
                last_run = self.state_store.get_last_run(task.name)
                if not is_task_due(now=run_at, last_run_at=last_run, interval_seconds=task.interval_seconds):
                    continue

                prompt = task.prompt_builder(context)
                if not prompt.strip():
                    raise ValueError("prompt must not be empty")

                task_started_at = time.monotonic()
                output = self.model_client.generate_text(prompt)
                report_path = self.report_writer.write(
                    task_name=task.name,
                    content=output,
                    generated_at=run_at,
                )
                duration_seconds = max(0.0, time.monotonic() - task_started_at)
                self.state_store.mark_run(
                    task_name=task.name,
                    run_at=run_at,
                    duration_seconds=duration_seconds,
                )
                generated_reports.append(report_path)
            except Exception as error:  # pragma: no cover - logging path
                self.logger.exception("task '%s' failed: %s", task.name, error)

        return generated_reports

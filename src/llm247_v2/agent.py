from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from llm247_v2.core.constitution import Constitution, load_constitution
from llm247_v2.core.directive import load_directive
from llm247_v2.discovery.pipeline import discover_and_evaluate
from llm247_v2.storage.experience import (
    ExperienceStore,
    extract_learnings,
    format_experiences_for_prompt,
    format_whats_learned,
)
from llm247_v2.discovery.exploration import load_exploration_map, save_exploration_map
from llm247_v2.discovery.interest import (
    InterestProfile,
    build_interest_profile,
    load_interest_profile,
    save_interest_profile,
)
from llm247_v2.execution.loop import ReActLoop, format_execution_log, serialize_trace
from llm247_v2.llm.client import BudgetExhaustedError, LLMClient, TokenTracker, client_for_point, extract_json
from llm247_v2.core.models import Directive, ModelBindingPoint, Task, TaskStatus
from llm247_v2.observability.observer import NullObserver, Observer
from llm247_v2.execution.safety import SafetyPolicy
from llm247_v2.storage.store import TaskStore
from llm247_v2.storage.thread_store import ThreadStore

logger = logging.getLogger("llm247_v2.agent")


class GracefulShutdown(Exception):
    """Raised when the agent detects a pending shutdown signal."""


class AutonomousAgentV2:
    """Scheduler: discover tasks, run the ReActLoop for each, record results.

    All execution decisions (git isolation, verification, commit) are made by
    the ReActLoop itself. This class only manages the cycle structure and
    cross-cutting concerns (token tracking, experience, observability).
    """

    # Maximum consecutive blocks before agent gives up on a task
    MAX_BLOCK_ATTEMPTS = 5

    def __init__(
        self,
        workspace: Path,
        store: TaskStore,
        llm: LLMClient,
        directive_path: Path,
        constitution_path: Path,
        exploration_map_path: Path,
        experience_store: Optional[ExperienceStore] = None,
        observer: Optional[Observer] = None,
        branch_prefix: str = "agent",
        interest_profile_path: Optional[Path] = None,
        shutdown_event: Optional[threading.Event] = None,
        thread_store: Optional[ThreadStore] = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.store = store
        self.llm = llm
        self.directive_path = directive_path
        self.constitution_path = constitution_path
        self.exploration_map_path = exploration_map_path
        self.interest_profile_path = interest_profile_path
        self.exp_store = experience_store
        self.obs = observer or NullObserver()
        self.branch_prefix = branch_prefix
        self._shutdown = shutdown_event or threading.Event()
        self.thread_store = thread_store

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown.is_set()

    def _check_shutdown(self, context: str = "") -> None:
        if self._shutdown.is_set():
            msg = f"Shutdown requested during {context}" if context else "Shutdown requested"
            logger.info(msg)
            raise GracefulShutdown(msg)

    def run_cycle(self) -> dict:
        self._check_shutdown("cycle start")

        directive = load_directive(self.directive_path)
        constitution = load_constitution(self.constitution_path)

        if directive.paused:
            self.obs.cycle_paused()
            return {"status": "paused", "reason": "directive.paused=true"}

        cycle_id = self.store.start_cycle()
        self.obs.cycle_start(cycle_id)

        summary = {
            "cycle_id": cycle_id,
            "tasks_discovered": 0,
            "tasks_executed": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
        }

        try:
            if self.thread_store:
                self._phase_check_thread_replies()
            summary["tasks_discovered"] = self._phase_discover(directive, constitution, cycle_id)
            self._check_shutdown("between discover and execute")
            executed, completed, failed = self._phase_execute(directive, constitution, cycle_id)
            summary["tasks_executed"] = executed
            summary["tasks_completed"] = completed
            summary["tasks_failed"] = failed

        except BudgetExhaustedError:
            summary["status"] = "budget_exhausted"
            self.obs.system_event("budget_exhausted", "Token budget depleted", success=False)
            raise
        except (KeyboardInterrupt, GracefulShutdown):
            summary["status"] = "interrupted"
            self.obs.system_event("interrupted", "Shutdown signal received mid-cycle")
            raise
        except Exception as exc:
            logger.exception("Cycle %d failed with unexpected error", cycle_id)
            summary["status"] = "error"
            self.obs.cycle_error(cycle_id, str(exc)[:300])
        finally:
            self.store.complete_cycle(
                cycle_id,
                tasks_discovered=summary["tasks_discovered"],
                tasks_executed=summary["tasks_executed"],
                tasks_completed=summary["tasks_completed"],
                tasks_failed=summary["tasks_failed"],
                summary=str(summary.get("status", "completed")),
            )
            self.obs.cycle_end(
                cycle_id,
                discovered=summary["tasks_discovered"],
                executed=summary["tasks_executed"],
                completed=summary["tasks_completed"],
                failed=summary["tasks_failed"],
            )
            self.obs.flush()

        return summary

    # ── Discovery ─────────────────────────────────────────────────────────────

    def _phase_discover(self, directive: Directive, constitution: Constitution, cycle_id: int) -> int:
        self._check_shutdown("discovery phase")

        existing_titles = {t.title for t in self.store.list_tasks(limit=200)}
        queued_count = len(self.store.list_tasks(status="queued", limit=100))
        emap = load_exploration_map(self.exploration_map_path)
        interest_profile = self._build_interest_profile(directive, emap)

        tasks, discovery_log = discover_and_evaluate(
            workspace=self.workspace,
            directive=directive,
            constitution=constitution,
            llm=self.llm,
            emap=emap,
            existing_titles=existing_titles,
            queued_count=queued_count,
            observer=self.obs,
            interest_profile=interest_profile,
        )

        save_exploration_map(self.exploration_map_path, emap)
        if self.interest_profile_path:
            save_interest_profile(self.interest_profile_path, interest_profile)

        if not tasks and "Skipping" in discovery_log:
            self.obs.discover_skipped(queued_count)
            return 0

        for task in tasks:
            task.status = TaskStatus.QUEUED.value
            task.cycle_id = cycle_id
            task.created_at = datetime.now(timezone.utc).isoformat()
            self.store.insert_task(task)
            self.obs.task_queued(task.id, task.title, task.source)

        return len(tasks)

    # ── Execution ─────────────────────────────────────────────────────────────

    def _phase_execute(self, directive: Directive, constitution: Constitution, cycle_id: int) -> tuple[int, int, int]:
        self._check_shutdown("execution phase")

        directive = load_directive(self.directive_path)
        if directive.paused:
            self.obs.system_event("execution_aborted", "directive changed to paused mid-cycle")
            return 0, 0, 0

        task = self.store.get_next_executable_task()
        if not task:
            self.obs.decision(
                "No tasks to execute",
                reasoning="No queued tasks, waiting for next discovery cycle",
            )
            return 0, 0, 0

        success = self._execute_single_task(task, directive, constitution)
        return 1, (1 if success else 0), (0 if success else 1)

    def _execute_single_task(self, task, directive: Directive, constitution: Constitution) -> bool:
        task_start_time = time.monotonic()
        token_tracker = _get_tracker(self.llm)
        token_before = token_tracker.snapshot() if token_tracker else None

        experience_context = self._get_experience_context(task)

        loop = ReActLoop(
            llm=client_for_point(self.llm, ModelBindingPoint.EXECUTION.value),
            constitution=constitution,
            observer=self.obs,
            shutdown_event=self._shutdown,
        )

        task.status = TaskStatus.EXECUTING.value
        self.store.update_task(task)

        def persist_loop_links(loop_state) -> None:
            task.branch_name = loop_state.branch_name
            task.pr_url = loop_state.pr_url
            self.store.update_task(task)

        success, trace, failure_reason, loop_state = loop.run(
            task=task,
            workspace=self.workspace,
            directive=directive,
            experience_context=experience_context,
            on_state_change=persist_loop_links,
        )

        task.execution_trace = serialize_trace(trace)
        task.execution_log = format_execution_log(trace)
        task.branch_name = loop_state.branch_name
        task.pr_url = loop_state.pr_url
        task.status = TaskStatus.COMPLETED.value if success else TaskStatus.NEEDS_HUMAN.value
        if not success:
            task.error_message = failure_reason or "ReActLoop ended without finish() — check execution trace"
            task.human_help_request = (
                f"Task '{task.title}' did not complete. "
                "Review the execution trace in the task detail view and resolve the blocking issue."
            )
        self._finalize_costs(task, task_start_time, token_tracker, token_before)
        self.store.update_task(task)

        if success:
            self.obs.task_completed(task.id, task.title)
            self._on_task_completed(task)
        else:
            self.obs.task_needs_human(task.id, task.error_message[:120])
            self._on_task_blocked(task)

        self.obs.system_event(
            "task_cost",
            f"tokens={task.token_cost} time={task.time_cost_seconds:.1f}s",
        )
        self._extract_and_store_learnings(task, "completed" if success else "failed")
        self._maybe_consolidate_experience()
        return success

    # ── Thread interaction ────────────────────────────────────────────────────

    def _phase_check_thread_replies(self) -> None:
        """Resume tasks that have received a human reply since last cycle."""
        assert self.thread_store
        for thread in self.thread_store.get_replied_threads():
            for task_id in self.thread_store.get_tasks_for_thread(thread.id):
                task = self.store.get_task(task_id)
                if task and task.status == TaskStatus.NEEDS_HUMAN.value:
                    task.status = TaskStatus.HUMAN_RESOLVED.value
                    task.human_help_request = ""
                    self.store.update_task(task)
            self.thread_store.set_status(thread.id, "waiting_reply")
            self.obs.system_event("thread_reply_processed", f"thread={thread.id}")

    def _on_task_blocked(self, task: Task) -> None:
        """Create or update a thread when the agent cannot proceed alone."""
        if not self.thread_store:
            return
        thread = self.thread_store.get_thread_for_task(task.id)
        if thread:
            attempt = self.thread_store.count_agent_messages(thread.id) + 1
            if attempt >= self.MAX_BLOCK_ATTEMPTS:
                self.thread_store.add_message(
                    thread.id, "agent",
                    f"Giving up after {attempt} attempt(s). Last error: "
                    f"{task.error_message or '(see task detail)'}",
                )
                self.thread_store.set_status(thread.id, "closed")
                task.status = TaskStatus.FAILED.value
                self.store.update_task(task)
            else:
                self.thread_store.add_message(
                    thread.id, "agent",
                    f"Still blocked (attempt {attempt}): "
                    f"{task.human_help_request or task.error_message or '(see task detail)'}",
                )
                self.thread_store.set_status(thread.id, "waiting_reply")
        else:
            body = (
                f"{task.human_help_request or 'Task did not complete — see execution trace.'}\n\n"
                f"Task: `{task.id}` | Source: {task.source}"
            )
            thread = self.thread_store.create_thread(
                title=task.title, created_by="agent", body=body
            )
            self.thread_store.link_task(thread.id, task.id)
            self.thread_store.set_status(thread.id, "waiting_reply")

    def _on_task_completed(self, task: Task) -> None:
        """Close thread when all linked tasks are done."""
        if not self.thread_store:
            return
        thread = self.thread_store.get_thread_for_task(task.id)
        if not thread:
            return
        all_task_ids = self.thread_store.get_tasks_for_thread(thread.id)
        all_done = all(
            (t := self.store.get_task(tid)) is not None and t.status in (
                TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value,
            )
            for tid in all_task_ids
        )
        if all_done:
            pr = f"\n\nPR: {task.pr_url}" if task.pr_url else ""
            self.thread_store.add_message(thread.id, "agent", f"Completed.{pr}")
            self.thread_store.set_status(thread.id, "closed")

    # ── Support ───────────────────────────────────────────────────────────────

    def _get_experience_context(self, task) -> str:
        if not self.exp_store:
            return ""
        relevant = self.exp_store.search(f"{task.title} {task.source}", limit=5)
        if not relevant:
            return ""
        for exp in relevant:
            self.exp_store.increment_applied(exp.id)
        summaries = "; ".join(e.summary[:60] for e in relevant)
        self.obs.experience_injected(task.id, len(relevant), summaries)
        return format_experiences_for_prompt(relevant)

    def _finalize_costs(self, task, start_time: float, tracker, snap_before) -> None:
        task.time_cost_seconds = round(time.monotonic() - start_time, 2)
        if tracker and snap_before:
            snap_after = tracker.snapshot()
            task.prompt_token_cost = snap_after["prompt_tokens"] - snap_before["prompt_tokens"]
            task.completion_token_cost = snap_after["completion_tokens"] - snap_before["completion_tokens"]
            task.token_cost = snap_after["total_tokens"] - snap_before["total_tokens"]

    def _extract_and_store_learnings(self, task, outcome: str) -> None:
        if not self.exp_store:
            return
        try:
            learnings = extract_learnings(
                task_title=task.title,
                task_source=task.source,
                task_id=task.id,
                execution_log=task.execution_log,
                verification_result="",
                error_message=task.error_message,
                outcome=outcome,
                llm_generate=client_for_point(self.llm, ModelBindingPoint.LEARNING_EXTRACTION.value).generate,
                extract_json_fn=extract_json,
            )
            if learnings:
                self.exp_store.add_batch(learnings)
                task.whats_learned = format_whats_learned(learnings)
                self.store.update_task(task)
                self.obs.system_event(
                    "learnings_extracted",
                    f"{len(learnings)} from task {task.id[:8]} ({outcome})",
                )
        except Exception as exc:
            logger.warning("Learning extraction failed for %s: %s", task.id, exc)

    def _build_interest_profile(self, directive: Directive, emap) -> InterestProfile:
        if self.interest_profile_path and self.interest_profile_path.exists():
            profile = load_interest_profile(self.interest_profile_path)
            for area in directive.focus_areas:
                if area not in profile.interests:
                    from llm247_v2.discovery.interest import Interest
                    profile.interests[area] = Interest(topic=area, strength=1.0, source="directive")
            return profile
        return build_interest_profile(directive, self.exp_store, emap)

    def _maybe_consolidate_experience(self) -> None:
        if not self.exp_store:
            return
        total = self.exp_store.count()
        if total < 10 or total % 10 != 0:
            return
        try:
            merged = self.exp_store.consolidate(
                llm_generate=client_for_point(self.llm, ModelBindingPoint.EXPERIENCE_MERGE.value).generate,
                extract_json_fn=extract_json,
            )
            if merged:
                self.obs.system_event("experience_consolidated",
                                      f"merged={merged} total_after={self.exp_store.count()}")
        except Exception as exc:
            logger.warning("Experience consolidation failed: %s", exc)


def run_agent_loop(
    agent: AutonomousAgentV2,
    poll_interval: int = 120,
    max_cycles: Optional[int] = None,
    sleeper=time.sleep,
) -> str:
    cycle_count = 0
    failure_streak = 0
    agent.obs.system_event("loop_started", f"poll={poll_interval}s max_cycles={max_cycles}")

    while max_cycles is None or cycle_count < max_cycles:
        if agent.shutdown_requested:
            agent.obs.system_event("loop_stopped", "shutdown event detected before cycle")
            return "interrupted"

        try:
            summary = agent.run_cycle()
            cycle_count += 1
            failure_streak = 0

            if summary.get("status") == "paused":
                sleeper(min(30, poll_interval) if poll_interval > 0 else 0)
                continue
            sleeper(poll_interval)

        except BudgetExhaustedError:
            agent.obs.system_event("loop_stopped", "budget exhausted", success=False)
            return "budget_exhausted"
        except (KeyboardInterrupt, GracefulShutdown):
            agent.obs.system_event("loop_stopped", "shutdown signal received")
            return "interrupted"
        except Exception:
            failure_streak += 1
            backoff = min(300, 2 ** min(failure_streak, 8))
            agent.obs.system_event("cycle_error",
                                   f"backing off {backoff}s (streak={failure_streak})", success=False)
            sleeper(backoff)

    agent.obs.system_event("loop_stopped", f"completed {cycle_count} cycles")
    return "max_cycles_reached"


def _get_tracker(llm) -> Optional[TokenTracker]:
    return getattr(llm, "tracker", None)


def _new_task_id() -> str:
    import uuid
    return uuid.uuid4().hex[:12]

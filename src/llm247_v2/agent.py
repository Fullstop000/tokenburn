from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from llm247_v2.core.constitution import Constitution, load_constitution
from llm247_v2.core.directive import load_directive
from llm247_v2.discovery.pipeline import discover_and_evaluate
from llm247_v2.execution.executor import PlanExecutor, format_execution_log
from llm247_v2.storage.experience import (
    ExperienceStore,
    extract_learnings,
    format_experiences_for_prompt,
    format_whats_learned,
)
from llm247_v2.discovery.exploration import load_exploration_map, save_exploration_map
from llm247_v2.execution.git_ops import GitOperationError, GitWorkflow
from llm247_v2.discovery.interest import (
    InterestProfile,
    build_interest_profile,
    load_interest_profile,
    save_interest_profile,
)
from llm247_v2.llm.client import BudgetExhaustedError, LLMClient, TokenTracker, extract_json
from llm247_v2.core.models import Directive, TaskStatus
from llm247_v2.observability.observer import NullObserver, Observer
from llm247_v2.execution.planner import (
    format_execution_history_for_replan,
    plan_task_with_constitution,
    replan_task_with_constitution,
    serialize_plan,
)
from llm247_v2.execution.safety import SafetyPolicy
from llm247_v2.storage.store import TaskStore
from llm247_v2.execution.verifier import format_verification, verify_task

logger = logging.getLogger("llm247_v2.agent")


class GracefulShutdown(Exception):
    """Raised when the agent detects a pending shutdown signal."""


class AutonomousAgentV2:
    """Main orchestrator: discover -> evaluate -> plan -> execute -> verify -> commit/PR.

    Tracks token cost and wall-clock time per task, extracts learnings after
    each task, and injects relevant past experiences into planning prompts.
    """

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
        command_timeout: int = 60,
        interest_profile_path: Optional[Path] = None,
        shutdown_event: Optional[threading.Event] = None,
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
        self.git = GitWorkflow(workspace, branch_prefix)
        self.safety = SafetyPolicy()
        self.command_timeout = command_timeout
        self._shutdown = shutdown_event or threading.Event()

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown.is_set()

    def _check_shutdown(self, context: str = "") -> None:
        """Raise GracefulShutdown if a stop signal has been received."""
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
            discovered = self._phase_discover(directive, constitution, cycle_id)
            summary["tasks_discovered"] = discovered

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

    def _phase_execute(self, directive: Directive, constitution: Constitution, cycle_id: int) -> tuple[int, int, int]:
        self._check_shutdown("execution phase")

        executed = 0
        completed = 0
        failed = 0

        directive = load_directive(self.directive_path)
        if directive.paused:
            self.obs.system_event("execution_aborted", "directive changed to paused mid-cycle")
            return executed, completed, failed

        task = self.store.get_next_executable_task()
        if not task:
            self.obs.decision(
                "No tasks to execute",
                reasoning="No queued or human-resolved tasks, waiting for next discovery cycle",
            )
            return executed, completed, failed

        executed += 1
        success = self._execute_single_task(task, directive, constitution)
        if success:
            completed += 1
        else:
            failed += 1

        return executed, completed, failed

    def _execute_single_task(self, task, directive: Directive, constitution: Constitution) -> bool:
        task_start_time = time.monotonic()
        token_tracker = _get_tracker(self.llm)
        token_before = token_tracker.snapshot() if token_tracker else None

        # Tasks resolved by humans bypass planning/execution and retry verification directly.
        if task.status == TaskStatus.HUMAN_RESOLVED.value:
            return self._continue_verification_after_human_resolution(task, task_start_time, token_tracker, token_before)

        # ── Retrieve relevant experiences ──
        experience_context = ""
        if self.exp_store:
            relevant = self.exp_store.search(f"{task.title} {task.source}", limit=5)
            if relevant:
                experience_context = format_experiences_for_prompt(relevant)
                for exp in relevant:
                    self.exp_store.increment_applied(exp.id)
                summaries = "; ".join(e.summary[:60] for e in relevant)
                self.obs.experience_injected(task.id, len(relevant), summaries)

        # ── Worktree isolation ──
        branch_name = ""
        worktree_path: Path | None = None
        execution_workspace = self.workspace

        try:
            branch_name, worktree_path = self.git.create_worktree(task.id, task.title)
            execution_workspace = worktree_path
            task.branch_name = branch_name
            task.status = TaskStatus.EXECUTING.value
            self.store.update_task(task)
            self.obs.git_worktree(task.id, branch_name, success=True)
        except GitOperationError as exc:
            task.status = TaskStatus.EXECUTING.value
            self.store.update_task(task)
            self.obs.git_worktree(task.id, str(exc)[:60], success=False)

        # ── Plan-Execute-Verify loop ──
        success, plan, results = self._plan_execute_verify_loop(
            task, directive, constitution, execution_workspace,
            experience_context, worktree_path, branch_name,
            token_tracker, token_before,
        )

        if not success:
            self._mark_task_needs_human(
                task,
                failure_message=task.error_message or "Execution failed after all replan rounds",
                human_request=task.human_help_request or self._build_help_request(
                    phase="Plan-Execute-Verify",
                    task=task,
                    what_happened="All replan rounds exhausted without success.",
                    blocking_reason=task.error_message or "unknown",
                    suggested_actions=[
                        "Review the replan history in the task detail view.",
                        f"Branch: `{branch_name}`" if branch_name else "No worktree branch.",
                        "Fix the issue and click Resolve.",
                    ],
                    plan_context=task.plan,
                ),
                task_start_time=task_start_time,
                token_tracker=token_tracker,
                token_before=token_before,
            )
            self._cleanup_worktree(branch_name, worktree_path)
            return False

        # ── Git workflow ──
        self._check_shutdown("git workflow")
        if branch_name and worktree_path:
            committed, commit_output = self.git.stage_and_commit(plan.commit_message, worktree_path)
            if committed:
                self.obs.git_committed(task.id, plan.commit_message)

                pushed, push_output = self.git.push_branch(branch_name, worktree_path)
                if pushed:
                    self.obs.git_pushed(task.id)

                    pr_ok, pr_output = self.git.create_pr(
                        plan.pr_title, plan.pr_body, worktree_path=worktree_path,
                    )
                    if pr_ok:
                        task.pr_url = pr_output
                    self.obs.git_pr(task.id, pr_output[:120], pr_ok)

            self.git.remove_worktree(worktree_path)

        # ── Finalize ──
        task.status = TaskStatus.COMPLETED.value
        task.human_help_request = ""
        self._finalize_costs(task, task_start_time, token_tracker, token_before)
        self.store.update_task(task)
        self.obs.task_completed(task.id, task.title)
        self.obs.system_event(
            "task_cost",
            f"tokens={task.token_cost} time={task.time_cost_seconds:.1f}s",
        )

        self._extract_and_store_learnings(task, "completed")
        self._maybe_consolidate_experience()
        return True

    def _plan_execute_verify_loop(
        self,
        task,
        directive: Directive,
        constitution: Constitution,
        execution_workspace: Path,
        experience_context: str,
        worktree_path: Path | None,
        branch_name: str,
        token_tracker,
        token_before,
    ) -> tuple[bool, TaskPlan | None, list]:
        """Run the plan-execute-verify loop with bounded re-planning.

        Returns (success, final_plan, final_results).
        """
        import json as _json

        max_rounds = directive.max_replan_rounds
        plan = None
        results = []
        trigger = ""
        verification_output = ""
        replan_rounds = []

        for round_num in range(max_rounds):
            # ── Plan or replan ──
            self._check_shutdown("task planning")

            if round_num == 0:
                task.status = TaskStatus.PLANNING.value
                self.store.update_task(task)
                self.obs.plan_started(task.id, task.title)

                plan = plan_task_with_constitution(
                    task, self.workspace, directive, constitution, self.llm,
                    experience_context=experience_context,
                )
                task.plan = serialize_plan(plan)
                self.store.update_task(task)
                self.obs.plan_created(task.id, len(plan.steps), plan.commit_message)
            else:
                executed_steps_text = format_execution_history_for_replan(results)
                remaining = max_rounds - round_num
                plan = replan_task_with_constitution(
                    task, self.workspace, directive, constitution, self.llm,
                    executed_steps=executed_steps_text,
                    verification_output=verification_output,
                    trigger=trigger,
                    round_number=round_num,
                    remaining_rounds=remaining,
                )
                task.plan = serialize_plan(plan)
                self.store.update_task(task)
                self.obs.replan_created(task.id, round_num, len(plan.steps))

            # ── Constitution check (every round) ──
            for step in plan.steps:
                allowed, reason = constitution.check_action_allowed(step.action, step.target)
                if not allowed:
                    self.obs.plan_blocked(task.id, reason)
                    task.error_message = f"Constitution blocked: {reason}"
                    task.human_help_request = self._build_help_request(
                        phase="Constitution Check",
                        task=task,
                        what_happened=f"The planned step `{step.action} {step.target}` was blocked by constitution policy.",
                        blocking_reason=reason,
                        suggested_actions=[
                            f"Edit constitution at {self.constitution_path} to allow `{step.action}` on `{step.target}`.",
                            "Or modify the task scope/description so the agent avoids this action.",
                            "Then click Resolve to let the agent re-plan this task.",
                        ],
                        plan_context=task.plan,
                    )
                    return (False, None, [])

            # ── Execute ──
            self._check_shutdown("task execution")
            task.status = TaskStatus.EXECUTING.value
            self.store.update_task(task)

            executor = PlanExecutor(
                workspace=execution_workspace,
                safety=self.safety,
                directive=directive,
                command_timeout=self.command_timeout,
                shutdown_event=self._shutdown,
            )
            all_ok, results = executor.execute_plan(plan)
            task.execution_log = format_execution_log(results)
            self.store.update_task(task)

            for i, r in enumerate(results):
                self.obs.execute_step(
                    task.id, i, len(results), r.action, r.target,
                    r.success, output=r.output[:100] if not r.success else "",
                )
            self.obs.execute_finished(task.id, all_ok)

            if not all_ok:
                # Record round
                self._append_replan_round(
                    task, replan_rounds, round_num, plan, results,
                    verification="", trigger="step_failure",
                )

                if round_num + 1 < max_rounds and not self._is_task_token_budget_exceeded(
                    directive, token_tracker, token_before
                ):
                    trigger = "step_failure"
                    verification_output = ""
                    self.obs.replan_triggered(task.id, round_num + 1, trigger)
                    continue

                # Exhausted
                self.obs.replan_exhausted(task.id, round_num + 1)
                error = results[-1].output[:300] if results else "unknown"
                failed_steps = [
                    f"  Step {r.step_index}: `{r.action} {r.target}` — {r.output[:150]}"
                    for r in results if not r.success
                ]
                task.error_message = f"Execution failed: {error}"
                task.human_help_request = self._build_help_request(
                    phase="Execution",
                    task=task,
                    what_happened=f"Execution failed after {round_num + 1} round(s).",
                    blocking_reason="\n".join(failed_steps) if failed_steps else error,
                    suggested_actions=[
                        "Check the failing step output above and fix the underlying issue in the workspace.",
                        f"Branch: `{branch_name}`" if branch_name else "No worktree branch (executed in main workspace).",
                        "Then click Resolve to let the agent re-verify.",
                    ],
                    plan_context=task.plan,
                )
                return (False, plan, results)

            # ── Verify ──
            self._check_shutdown("task verification")
            task.status = TaskStatus.VERIFYING.value
            self.store.update_task(task)

            changed_files = [r.target for r in results if r.action in ("edit_file", "create_file") and r.success]
            verification = verify_task(execution_workspace, changed_files)
            task.verification_result = format_verification(verification)
            self.store.update_task(task)
            self.obs.verify_result(task.id, verification.passed, verification.summary)
            verification_output = format_verification(verification)

            if not verification.passed:
                # Record round
                self._append_replan_round(
                    task, replan_rounds, round_num, plan, results,
                    verification=verification_output, trigger="verification_failure",
                )

                if round_num + 1 < max_rounds and not self._is_task_token_budget_exceeded(
                    directive, token_tracker, token_before
                ):
                    trigger = "verification_failure"
                    self.obs.replan_triggered(task.id, round_num + 1, trigger)
                    continue

                # Exhausted
                self.obs.replan_exhausted(task.id, round_num + 1)
                failed_checks = [
                    f"  [{c.name}] {c.output[:200]}"
                    for c in verification.checks if not c.passed
                ]
                task.error_message = f"Verification failed: {verification.summary}"
                task.human_help_request = self._build_help_request(
                    phase="Verification",
                    task=task,
                    what_happened=f"Verification failed after {round_num + 1} round(s).",
                    blocking_reason="\n".join(failed_checks) if failed_checks else verification.summary,
                    suggested_actions=[
                        "Review the failing checks above and fix the issues in the workspace.",
                        f"Changed files: {', '.join(f'`{f}`' for f in changed_files)}" if changed_files else "No changed files recorded.",
                        f"Branch: `{branch_name}`" if branch_name else "No worktree branch.",
                        "Then click Resolve to let the agent re-run verification.",
                    ],
                    plan_context=task.plan,
                )
                return (False, plan, results)

            # Success!
            return (True, plan, results)

        # Should not reach here, but just in case
        return (False, plan, results)

    def _append_replan_round(self, task, rounds_list, round_num, plan, results, verification, trigger):
        """Append a round summary to the replan history."""
        import json as _json

        round_data = {
            "round_number": round_num,
            "plan_steps": [
                {"action": s.action, "target": s.target, "description": s.description}
                for s in plan.steps
            ],
            "results": [
                {"step_index": r.step_index, "action": r.action, "target": r.target,
                 "success": r.success, "output": r.output[:300]}
                for r in results
            ],
            "verification": verification,
            "trigger": trigger,
        }
        rounds_list.append(round_data)
        task.replan_history = _json.dumps(rounds_list, ensure_ascii=False)
        self.store.update_task(task)

    def _is_task_token_budget_exceeded(self, directive, token_tracker, token_before) -> bool:
        if directive.max_tokens_per_task <= 0:
            return False
        if not token_tracker or not token_before:
            return False
        current = token_tracker.snapshot()["total_tokens"] - token_before["total_tokens"]
        return current >= directive.max_tokens_per_task

    def _continue_verification_after_human_resolution(self, task, task_start_time: float, token_tracker, token_before) -> bool:
        """Resume verification for a task after human manually resolved blocking issues."""
        self._check_shutdown("verification retry after human resolution")

        task.status = TaskStatus.VERIFYING.value
        task.error_message = ""
        self.store.update_task(task)

        changed_files = self._extract_changed_files_from_execution_log(task.execution_log)
        verification = verify_task(self.workspace, changed_files)
        task.verification_result = format_verification(verification)
        self.store.update_task(task)
        self.obs.verify_result(task.id, verification.passed, verification.summary)

        if not verification.passed:
            failed_checks = [
                f"  [{c.name}] {c.output[:200]}"
                for c in verification.checks if not c.passed
            ]
            self._mark_task_needs_human(
                task,
                failure_message=f"Verification failed after human resolve: {verification.summary}",
                human_request=self._build_help_request(
                    phase="Re-verification (after human resolve)",
                    task=task,
                    what_happened="Verification still fails after your previous fix. The issue was not fully resolved.",
                    blocking_reason="\n".join(failed_checks) if failed_checks else verification.summary,
                    suggested_actions=[
                        "Review the remaining failures above.",
                        f"Previously changed files: {', '.join(f'`{f}`' for f in changed_files)}" if changed_files else "Could not determine changed files from log.",
                        "Fix the remaining issues and click Resolve again.",
                    ],
                ),
                task_start_time=task_start_time,
                token_tracker=token_tracker,
                token_before=token_before,
            )
            return False

        task.status = TaskStatus.COMPLETED.value
        task.human_help_request = ""
        self._finalize_costs(task, task_start_time, token_tracker, token_before)
        self.store.update_task(task)
        self.obs.task_completed(task.id, task.title)
        self.obs.system_event(
            "task_cost",
            f"tokens={task.token_cost} time={task.time_cost_seconds:.1f}s",
        )
        self._extract_and_store_learnings(task, "completed")
        self._maybe_consolidate_experience()
        return True

    def _mark_task_needs_human(
        self,
        task,
        *,
        failure_message: str,
        human_request: str,
        task_start_time: float,
        token_tracker,
        token_before,
    ) -> bool:
        """Persist a blocked task as needs_human with a concrete request for a human."""
        task.status = TaskStatus.NEEDS_HUMAN.value
        task.error_message = failure_message
        task.human_help_request = human_request
        self._finalize_costs(task, task_start_time, token_tracker, token_before)
        self.store.update_task(task)
        self.obs.task_needs_human(task.id, failure_message[:120])
        self.obs.system_event(
            "help_requested",
            f"task={task.id[:8]} {human_request[:200]}",
            success=False,
        )
        self._extract_and_store_learnings(task, "failed")
        return False

    @staticmethod
    def _build_help_request(
        *,
        phase: str,
        task,
        what_happened: str,
        blocking_reason: str,
        suggested_actions: list[str],
        plan_context: str = "",
    ) -> str:
        """Build a structured, actionable help request for the human dashboard."""
        lines = [
            f"## Task: {task.title}",
            f"   ID: {task.id}  |  Source: {task.source}  |  Branch: {task.branch_name or 'N/A'}",
            "",
            f"## Blocked at: {phase}",
            "",
            f"### What happened",
            what_happened,
            "",
            f"### Error detail",
            blocking_reason[:1500],
        ]
        if plan_context:
            lines += ["", "### Execution plan (for reference)", plan_context[:800]]
        lines += ["", "### Suggested actions"]
        for i, action in enumerate(suggested_actions, 1):
            lines.append(f"  {i}. {action}")
        return "\n".join(lines)

    _LOG_LINE_RE = re.compile(
        r"^\[\d+\]\s+OK\s+(edit_file|create_file|replace_in_file)\s+(\S+)"
    )

    @classmethod
    def _extract_changed_files_from_execution_log(cls, execution_log: str) -> list[str]:
        """Recover changed file targets from execution log for verification retries."""
        changed_files: list[str] = []
        for line in execution_log.splitlines():
            m = cls._LOG_LINE_RE.match(line.strip())
            if not m:
                continue
            target = m.group(2)
            if target not in changed_files:
                changed_files.append(target)
        return changed_files

    def _finalize_costs(self, task, start_time: float, tracker, snap_before) -> None:
        task.time_cost_seconds = round(time.monotonic() - start_time, 2)
        if tracker and snap_before:
            snap_after = tracker.snapshot()
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
                verification_result=task.verification_result,
                error_message=task.error_message,
                outcome=outcome,
                llm_generate=self.llm.generate,
                extract_json_fn=extract_json,
            )
            if learnings:
                self.exp_store.add_batch(learnings)
                task.whats_learned = format_whats_learned(learnings)
                self.store.update_task(task)
                self.obs.system_event(
                    "learnings_extracted",
                    f"{len(learnings)} from task {task.id[:8]} ({outcome})",
                    success=True,
                )
        except Exception as exc:
            logger.warning("Learning extraction failed for %s: %s", task.id, exc)
            self.obs.system_event(
                "learning_extraction_failed",
                f"task={task.id[:8]} error={str(exc)[:200]}",
                success=False,
            )

    def _build_interest_profile(self, directive: Directive, emap) -> InterestProfile:
        """Build the agent's interest profile from all available signals."""
        if self.interest_profile_path and self.interest_profile_path.exists():
            profile = load_interest_profile(self.interest_profile_path)
            for area in directive.focus_areas:
                if area not in profile.interests:
                    from llm247_v2.discovery.interest import Interest
                    profile.interests[area] = Interest(topic=area, strength=1.0, source="directive")
            return profile
        return build_interest_profile(directive, self.exp_store, emap)

    def _maybe_consolidate_experience(self) -> None:
        """Run experience consolidation every 10 completed tasks."""
        if not self.exp_store:
            return
        total = self.exp_store.count()
        if total < 10 or total % 10 != 0:
            return
        try:
            merged = self.exp_store.consolidate(
                llm_generate=self.llm.generate,
                extract_json_fn=extract_json,
            )
            if merged:
                self.obs.system_event("experience_consolidated", f"merged={merged} total_after={self.exp_store.count()}")
        except Exception as exc:
            logger.warning("Experience consolidation failed: %s", exc)

    def _cleanup_worktree(self, branch_name: str, worktree_path: Path | None) -> None:
        if worktree_path and branch_name:
            try:
                self.git.cleanup_branch(branch_name, worktree_path)
            except Exception:
                self.obs.system_event("cleanup_failed", f"worktree={worktree_path}", success=False)


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
            agent.obs.system_event("cycle_error", f"backing off {backoff}s (streak={failure_streak})", success=False)
            sleeper(backoff)

    agent.obs.system_event("loop_stopped", f"completed {cycle_count} cycles")
    return "max_cycles_reached"


def _get_tracker(llm) -> Optional[TokenTracker]:
    return getattr(llm, "tracker", None)

from __future__ import annotations

import json
import logging
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Protocol, Tuple

from llm247.ark_client import BudgetExhaustedError
from llm247.context import collect_git_status, collect_recent_commits, collect_recent_reports, collect_todo_items
from llm247.reports import ReportWriter


@dataclass(frozen=True)
class AgentAction:
    """One executable action emitted by the autonomous planner."""

    action_type: str
    command: Optional[List[str]] = None
    query: str = ""
    path: str = ""
    content: str = ""


@dataclass(frozen=True)
class ActionResult:
    """Execution result for one agent action."""

    action_type: str
    success: bool
    output: str


@dataclass(frozen=True)
class AutonomousPlan:
    """Planner output for one autonomous cycle."""

    goal: str
    topic_query: str
    actions: List[AgentAction]
    rationale: str


@dataclass(frozen=True)
class PlannerContext:
    """Context available to planner for deciding the next steps."""

    workspace_path: Path
    now: datetime
    workspace_summary: str
    previous_goal: str
    previous_topic_query: str
    last_cycle_observations: str
    recent_reports: str


@dataclass(frozen=True)
class AutonomousState:
    """Persisted autonomous runtime state across process restarts."""

    active_goal: str = ""
    previous_topic_query: str = ""
    cycle_count: int = 0
    last_cycle_observations: str = ""
    current_task: str = ""
    current_task_iteration: int = 0
    current_task_elapsed_seconds: float = 0.0
    progress_completed_actions: int = 0
    progress_total_actions: int = 0
    status: str = "idle"
    pending_goal: str = ""
    pending_topic_query: str = ""
    pending_rationale: str = ""
    pending_actions: List[AgentAction] = field(default_factory=list)
    stop_reason: str = ""
    updated_at: str = ""


class PlannerModelClient(Protocol):
    """Planner-facing model client contract."""

    def generate_text(self, prompt: str) -> str:
        """Generate plain text from a planning prompt."""


class AutonomousStateStore:
    """Durable state store for autonomous runtime progress and stop reason."""

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path

    def load(self) -> AutonomousState:
        """Load state from disk with corruption-safe fallback."""
        if not self.state_path.exists():
            return AutonomousState()

        try:
            raw_data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(raw_data, dict):
                return AutonomousState()
            return AutonomousState(
                active_goal=str(raw_data.get("active_goal", "")),
                previous_topic_query=str(raw_data.get("previous_topic_query", "")),
                cycle_count=int(raw_data.get("cycle_count", 0)),
                last_cycle_observations=str(raw_data.get("last_cycle_observations", "")),
                current_task=str(raw_data.get("current_task", "")),
                current_task_iteration=int(raw_data.get("current_task_iteration", 0)),
                current_task_elapsed_seconds=float(raw_data.get("current_task_elapsed_seconds", 0.0)),
                progress_completed_actions=int(raw_data.get("progress_completed_actions", 0)),
                progress_total_actions=int(raw_data.get("progress_total_actions", 0)),
                status=str(raw_data.get("status", "idle")),
                pending_goal=str(raw_data.get("pending_goal", "")),
                pending_topic_query=str(raw_data.get("pending_topic_query", "")),
                pending_rationale=str(raw_data.get("pending_rationale", "")),
                pending_actions=_load_pending_actions(raw_data.get("pending_actions", [])),
                stop_reason=str(raw_data.get("stop_reason", "")),
                updated_at=str(raw_data.get("updated_at", "")),
            )
        except (OSError, ValueError, json.JSONDecodeError):
            return AutonomousState()

    def save(self, state: AutonomousState) -> None:
        """Persist state atomically to avoid partial writes."""
        payload = {
            "active_goal": state.active_goal,
            "previous_topic_query": state.previous_topic_query,
            "cycle_count": state.cycle_count,
            "last_cycle_observations": state.last_cycle_observations,
            "current_task": state.current_task,
            "current_task_iteration": state.current_task_iteration,
            "current_task_elapsed_seconds": state.current_task_elapsed_seconds,
            "progress_completed_actions": state.progress_completed_actions,
            "progress_total_actions": state.progress_total_actions,
            "status": state.status,
            "pending_goal": state.pending_goal,
            "pending_topic_query": state.pending_topic_query,
            "pending_rationale": state.pending_rationale,
            "pending_actions": [_dump_action(action) for action in state.pending_actions],
            "stop_reason": state.stop_reason,
            "updated_at": state.updated_at,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(self.state_path)


class CommandSafetyPolicy:
    """Allow-list based command policy for autonomous shell execution."""

    def __init__(self) -> None:
        self.allowed_binaries = {
            "ls",
            "pwd",
            "cat",
            "echo",
            "rg",
            "find",
            "head",
            "tail",
            "wc",
            "sed",
            "mkdir",
            "touch",
            "cp",
            "mv",
            "git",
            "python3",
        }

    def is_allowed(self, command: List[str]) -> Tuple[bool, str]:
        """Check whether one tokenized command is safe to execute."""
        if not command:
            return False, "empty command"

        program = command[0]
        if program not in self.allowed_binaries:
            return False, f"program not in allow-list: {program}"

        if program == "git":
            return self._check_git(command)

        if program == "python3":
            return self._check_python(command)

        return True, "allowed"

    def _check_git(self, command: List[str]) -> Tuple[bool, str]:
        """Restrict git usage to safe read-only subcommands."""
        if len(command) < 2:
            return False, "git subcommand is required"

        allowed_subcommands = {"status", "diff", "log", "rev-parse", "branch"}
        if command[1] not in allowed_subcommands:
            return False, f"git subcommand blocked: {command[1]}"
        return True, "allowed"

    def _check_python(self, command: List[str]) -> Tuple[bool, str]:
        """Restrict python3 invocation to test runners only."""
        if len(command) >= 3 and command[1] == "-m" and command[2] in {"unittest", "pytest"}:
            return True, "allowed"
        return False, "python3 is limited to test runner modules"


@dataclass(frozen=True)
class WebSearchResult:
    """One lightweight internet search result item."""

    title: str
    url: str
    snippet: str


class WebSearchClient:
    """Internet search client backed by public Hacker News search API."""

    def __init__(self, result_limit: int = 5, timeout_seconds: int = 15) -> None:
        self.result_limit = result_limit
        self.timeout_seconds = timeout_seconds

    def search(self, query: str) -> List[WebSearchResult]:
        """Search internet topics and return structured results."""
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        try:
            encoded_query = urllib.parse.quote(cleaned_query)
            url = f"https://hn.algolia.com/api/v1/search?tags=story&query={encoded_query}"
            request = urllib.request.Request(url=url, headers={"User-Agent": "llm247-autonomous-agent"})
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        except (OSError, ValueError, json.JSONDecodeError):
            return []

        hits = payload.get("hits", []) if isinstance(payload, dict) else []
        results: List[WebSearchResult] = []
        for item in hits:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("story_title") or "Untitled")
            link = str(item.get("url") or item.get("story_url") or "")
            snippet = str(item.get("story_text") or item.get("comment_text") or "")
            if not link:
                continue
            results.append(WebSearchResult(title=title, url=link, snippet=snippet[:280]))
            if len(results) >= self.result_limit:
                break

        return results


class AutonomousPlanner:
    """LLM planner that self-defines goals and executable actions each cycle."""

    def __init__(self, model_client: PlannerModelClient, max_actions: int = 5) -> None:
        if max_actions <= 0:
            raise ValueError("max_actions must be greater than 0")

        self.model_client = model_client
        self.max_actions = max_actions

    def build_plan(self, context: PlannerContext) -> AutonomousPlan:
        """Generate a structured plan from runtime context."""
        prompt = self._build_prompt(context)
        raw_output = self.model_client.generate_text(prompt)
        return self._parse_plan(raw_output=raw_output, context=context)

    def _build_prompt(self, context: PlannerContext) -> str:
        """Build constrained planning prompt with JSON-only output contract."""
        return (
            "你是 7x24 自治工程代理。你的目标不是执行固定任务，而是自己设定目标并推进实现。\n"
            "要求：\n"
            "1) 自主设置一个当前最有价值的工程目标。\n"
            "2) 给出一个互联网搜索 query（topic_query）。\n"
            "3) 生成可执行 action 列表。\n"
            "4) action 只能使用以下类型：search_web, run_command, write_file, append_file。\n"
            "5) run_command 必须是 tokenized 数组，不允许 shell 拼接。\n"
            "6) 输出必须是 JSON，不要 markdown。\n\n"
            "JSON schema:\n"
            "{\n"
            "  \"goal\": \"...\",\n"
            "  \"topic_query\": \"...\",\n"
            "  \"rationale\": \"...\",\n"
            "  \"actions\": [\n"
            "    {\"type\": \"search_web\", \"query\": \"...\"},\n"
            "    {\"type\": \"run_command\", \"command\": [\"rg\", \"--files\"]},\n"
            "    {\"type\": \"write_file\", \"path\": \"notes/next.md\", \"content\": \"...\"}\n"
            "  ]\n"
            "}\n\n"
            f"当前时间(UTC): {context.now.isoformat()}\n"
            f"工作区: {context.workspace_path}\n\n"
            "### 工作区摘要\n"
            f"{context.workspace_summary}\n\n"
            "### 最近报告\n"
            f"{context.recent_reports}\n\n"
            "### 上一轮状态\n"
            f"previous_goal: {context.previous_goal}\n"
            f"previous_topic_query: {context.previous_topic_query}\n"
            f"last_cycle_observations: {context.last_cycle_observations}\n"
        )

    def _parse_plan(self, raw_output: str, context: PlannerContext) -> AutonomousPlan:
        """Parse planner JSON and fallback to minimal safe plan on errors."""
        json_payload = _extract_first_json_object(raw_output)
        if not json_payload:
            return self._fallback_plan(context)

        try:
            parsed = json.loads(json_payload)
            if not isinstance(parsed, dict):
                return self._fallback_plan(context)
        except (ValueError, json.JSONDecodeError):
            return self._fallback_plan(context)

        goal = str(parsed.get("goal", "")).strip() or "Autonomously improve repository quality"
        topic_query = str(parsed.get("topic_query", "")).strip() or "software engineering trends"
        rationale = str(parsed.get("rationale", "")).strip() or "Adaptive autonomous loop"

        raw_actions = parsed.get("actions", [])
        actions: List[AgentAction] = []
        if isinstance(raw_actions, list):
            for item in raw_actions:
                action = _parse_action(item)
                if action is not None:
                    actions.append(action)
                if len(actions) >= self.max_actions:
                    break

        if not actions:
            actions = [
                AgentAction(action_type="search_web", query=topic_query),
                AgentAction(action_type="run_command", command=["rg", "--files"]),
            ][: self.max_actions]

        return AutonomousPlan(goal=goal, topic_query=topic_query, actions=actions, rationale=rationale)

    def _fallback_plan(self, context: PlannerContext) -> AutonomousPlan:
        """Create a deterministic minimal plan when model output is invalid."""
        fallback_query = context.previous_topic_query or "software engineering automation"
        fallback_goal = context.previous_goal or "Discover and implement one useful engineering improvement"
        return AutonomousPlan(
            goal=fallback_goal,
            topic_query=fallback_query,
            rationale="Fallback plan due to invalid planner JSON",
            actions=[
                AgentAction(action_type="search_web", query=fallback_query),
                AgentAction(action_type="run_command", command=["rg", "--files"]),
            ][: self.max_actions],
        )


class SafeActionExecutor:
    """Execute autonomous actions under strict safety and path boundaries."""

    def __init__(
        self,
        safety_policy: CommandSafetyPolicy,
        web_search_client: WebSearchClient,
        command_timeout_seconds: int = 60,
        max_file_bytes: int = 200_000,
    ) -> None:
        self.safety_policy = safety_policy
        self.web_search_client = web_search_client
        self.command_timeout_seconds = command_timeout_seconds
        self.max_file_bytes = max_file_bytes

    def execute(self, action: AgentAction, workspace_path: Path) -> ActionResult:
        """Execute one action and capture normalized output."""
        try:
            if action.action_type == "search_web":
                return self._execute_search(action)
            if action.action_type == "run_command":
                return self._execute_command(action, workspace_path)
            if action.action_type == "write_file":
                return self._execute_write(action, workspace_path, append=False)
            if action.action_type == "append_file":
                return self._execute_write(action, workspace_path, append=True)
            return ActionResult(action_type=action.action_type, success=False, output="unsupported action")
        except Exception as error:  # pragma: no cover - defensive guard
            return ActionResult(action_type=action.action_type, success=False, output=f"execution error: {error}")

    def _execute_search(self, action: AgentAction) -> ActionResult:
        """Execute web search and render compact result list."""
        results = self.web_search_client.search(action.query)
        if not results:
            return ActionResult(action_type="search_web", success=False, output="no search results")

        rendered = "\n".join(
            f"- {item.title} | {item.url} | {item.snippet}" for item in results
        )
        return ActionResult(action_type="search_web", success=True, output=rendered)

    def _execute_command(self, action: AgentAction, workspace_path: Path) -> ActionResult:
        """Execute allow-listed command in workspace with timeout."""
        command = action.command or []
        is_allowed, reason = self.safety_policy.is_allowed(command)
        if not is_allowed:
            return ActionResult(action_type="run_command", success=False, output=f"blocked by safety policy: {reason}")

        completed = subprocess.run(
            command,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=self.command_timeout_seconds,
            check=False,
        )
        output = completed.stdout.strip() or completed.stderr.strip() or "<empty>"
        return ActionResult(action_type="run_command", success=completed.returncode == 0, output=output[:8000])

    def _execute_write(self, action: AgentAction, workspace_path: Path, append: bool) -> ActionResult:
        """Write or append file under workspace with path traversal protection."""
        if not action.path:
            return ActionResult(action_type=action.action_type, success=False, output="missing path")

        if len(action.content.encode("utf-8")) > self.max_file_bytes:
            return ActionResult(action_type=action.action_type, success=False, output="content too large")

        target_path = _resolve_workspace_path(workspace_path, action.path)
        if target_path is None:
            return ActionResult(action_type=action.action_type, success=False, output="path out of workspace")
        if ".git" in target_path.parts:
            return ActionResult(action_type=action.action_type, success=False, output="writing inside .git is blocked")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with target_path.open(mode, encoding="utf-8") as file_obj:
            file_obj.write(action.content)
        return ActionResult(action_type=action.action_type, success=True, output=f"wrote {target_path}")


class AutonomousAgent:
    """Autonomous goal-setting agent that plans and executes one cycle at a time."""

    def __init__(
        self,
        workspace_path: Path,
        planner: AutonomousPlanner,
        executor: SafeActionExecutor,
        state_store: AutonomousStateStore,
        report_writer: ReportWriter,
    ) -> None:
        self.workspace_path = workspace_path
        self.planner = planner
        self.executor = executor
        self.state_store = state_store
        self.report_writer = report_writer
        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            self.logger.addHandler(logging.NullHandler())

    def run_once(self, now: Optional[datetime] = None) -> Path:
        """Run one autonomous cycle and persist report/state."""
        run_at = now or datetime.now(timezone.utc)
        cycle_started_at = time.monotonic()
        state = self.state_store.load()
        resumed_from_pending = bool(state.pending_actions)
        _log_lifecycle_event(
            event="autonomous_cycle_started",
            cycle_count=state.cycle_count + 1,
            previous_goal=state.active_goal,
            resumed_from_pending=resumed_from_pending,
            pending_actions=len(state.pending_actions),
        )

        if resumed_from_pending:
            plan = AutonomousPlan(
                goal=state.pending_goal or state.active_goal or "Resume unfinished autonomous task",
                topic_query=state.pending_topic_query or state.previous_topic_query,
                actions=list(state.pending_actions),
                rationale=state.pending_rationale or "Resuming pending actions after interruption",
            )
        else:
            context = PlannerContext(
                workspace_path=self.workspace_path,
                now=run_at,
                workspace_summary=self._build_workspace_summary(),
                previous_goal=state.active_goal,
                previous_topic_query=state.previous_topic_query,
                last_cycle_observations=state.last_cycle_observations,
                recent_reports=collect_recent_reports(self.report_writer.report_dir),
            )
            plan = self.planner.build_plan(context)

        task_iteration = _next_task_iteration(state=state, goal=plan.goal, resumed_from_pending=resumed_from_pending)
        base_elapsed_seconds = _task_base_elapsed_seconds(
            state=state,
            goal=plan.goal,
            resumed_from_pending=resumed_from_pending,
        )
        action_results: List[ActionResult] = []
        observations = state.last_cycle_observations
        remaining_actions = list(plan.actions)
        self._save_pending_state(
            state=state,
            plan=plan,
            task_iteration=task_iteration,
            task_elapsed_seconds=base_elapsed_seconds,
            pending_actions=remaining_actions,
            run_at=run_at,
            last_cycle_observations=state.last_cycle_observations,
        )

        for action in plan.actions:
            action_results.append(self.executor.execute(action=action, workspace_path=self.workspace_path))
            remaining_actions = remaining_actions[1:]
            elapsed_seconds = base_elapsed_seconds + max(0.0, time.monotonic() - cycle_started_at)
            observations = "\n".join(
                f"[{result.action_type}] success={result.success} output={result.output[:280]}"
                for result in action_results
            )
            self._save_pending_state(
                state=state,
                plan=plan,
                task_iteration=task_iteration,
                task_elapsed_seconds=elapsed_seconds,
                pending_actions=remaining_actions,
                run_at=run_at,
                last_cycle_observations=observations,
            )

        report_content = self._build_cycle_report(plan=plan, action_results=action_results, run_at=run_at)
        report_path = self.report_writer.write(
            task_name="autonomous_agent",
            content=report_content,
            generated_at=run_at,
        )

        observations = "\n".join(
            f"[{result.action_type}] success={result.success} output={result.output[:280]}"
            for result in action_results
        )
        total_elapsed_seconds = base_elapsed_seconds + max(0.0, time.monotonic() - cycle_started_at)
        self.state_store.save(
            AutonomousState(
                active_goal=plan.goal,
                previous_topic_query=plan.topic_query,
                cycle_count=state.cycle_count + 1,
                last_cycle_observations=observations,
                current_task=plan.goal,
                current_task_iteration=task_iteration,
                current_task_elapsed_seconds=total_elapsed_seconds,
                progress_completed_actions=len(plan.actions),
                progress_total_actions=len(plan.actions),
                status="completed",
                pending_goal="",
                pending_topic_query="",
                pending_rationale="",
                pending_actions=[],
                stop_reason="",
                updated_at=run_at.isoformat(),
            )
        )
        _log_lifecycle_event(
            event="autonomous_cycle_completed",
            cycle_count=state.cycle_count + 1,
            goal=plan.goal,
            actions=len(plan.actions),
            report=str(report_path),
            resumed_from_pending=resumed_from_pending,
        )

        return report_path

    def mark_stopped(self, reason: str, now: Optional[datetime] = None) -> None:
        """Persist stop reason when loop exits intentionally."""
        run_at = now or datetime.now(timezone.utc)
        state = self.state_store.load()
        self.state_store.save(
            AutonomousState(
                active_goal=state.active_goal,
                previous_topic_query=state.previous_topic_query,
                cycle_count=state.cycle_count,
                last_cycle_observations=state.last_cycle_observations,
                current_task=state.current_task,
                current_task_iteration=state.current_task_iteration,
                current_task_elapsed_seconds=state.current_task_elapsed_seconds,
                progress_completed_actions=state.progress_completed_actions,
                progress_total_actions=state.progress_total_actions,
                status=reason,
                pending_goal=state.pending_goal,
                pending_topic_query=state.pending_topic_query,
                pending_rationale=state.pending_rationale,
                pending_actions=list(state.pending_actions),
                stop_reason=reason,
                updated_at=run_at.isoformat(),
            )
        )
        _log_lifecycle_event(event="autonomous_loop_marked_stopped", reason=reason)

    def _save_pending_state(
        self,
        state: AutonomousState,
        plan: AutonomousPlan,
        task_iteration: int,
        task_elapsed_seconds: float,
        pending_actions: List[AgentAction],
        run_at: datetime,
        last_cycle_observations: str,
    ) -> None:
        """Persist unfinished actions so shutdown can resume from latest progress."""
        completed_actions = max(0, len(plan.actions) - len(pending_actions))
        total_actions = len(plan.actions)
        self.state_store.save(
            AutonomousState(
                active_goal=plan.goal,
                previous_topic_query=state.previous_topic_query,
                cycle_count=state.cycle_count,
                last_cycle_observations=last_cycle_observations,
                current_task=plan.goal,
                current_task_iteration=task_iteration,
                current_task_elapsed_seconds=max(0.0, task_elapsed_seconds),
                progress_completed_actions=completed_actions,
                progress_total_actions=total_actions,
                status="running",
                pending_goal=plan.goal,
                pending_topic_query=plan.topic_query,
                pending_rationale=plan.rationale,
                pending_actions=list(pending_actions),
                stop_reason="",
                updated_at=run_at.isoformat(),
            )
        )

    def _build_workspace_summary(self) -> str:
        """Build lightweight repo summary for planner input."""
        git_status = collect_git_status(self.workspace_path)
        commits = collect_recent_commits(self.workspace_path)
        todos = collect_todo_items(self.workspace_path)
        return (
            "### Git Status\n"
            f"{git_status}\n\n"
            "### Recent Commits\n"
            f"{commits}\n\n"
            "### TODO/FIXME/BUG\n"
            f"{todos}\n"
        )

    def _build_cycle_report(self, plan: AutonomousPlan, action_results: List[ActionResult], run_at: datetime) -> str:
        """Render markdown report for observability and future memory."""
        lines = [
            "# Autonomous Cycle Report",
            "",
            f"- time(UTC): {run_at.isoformat()}",
            f"- goal: {plan.goal}",
            f"- topic_query: {plan.topic_query}",
            f"- rationale: {plan.rationale}",
            "",
            "## Actions",
        ]

        for index, action in enumerate(plan.actions, start=1):
            lines.append(f"### {index}. {action.action_type}")
            if action.command:
                lines.append(f"- command: {action.command}")
            if action.query:
                lines.append(f"- query: {action.query}")
            if action.path:
                lines.append(f"- path: {action.path}")
            if action.content:
                lines.append(f"- content-preview: {action.content[:120]}")

        lines.append("")
        lines.append("## Results")
        for result in action_results:
            lines.append(f"- [{result.action_type}] success={result.success}")
            lines.append("```")
            lines.append(result.output[:1200])
            lines.append("```")

        return "\n".join(lines) + "\n"


# Drive autonomous loop until budget exhaustion or external interruption.
def run_autonomous_loop(
    agent: AutonomousAgent,
    poll_interval_seconds: int,
    max_cycles: Optional[int] = None,
    sleeper=time.sleep,
) -> str:
    """Run agent repeatedly and stop only on explicit terminal reasons."""
    logger = logging.getLogger("llm247.autonomous")
    cycle_count = 0
    failure_count = 0

    while max_cycles is None or cycle_count < max_cycles:
        try:
            report_path = agent.run_once(now=datetime.now(timezone.utc))
            logger.info("autonomous cycle complete: report=%s", report_path)
            failure_count = 0
            cycle_count += 1
            sleeper(poll_interval_seconds)
        except BudgetExhaustedError:
            agent.mark_stopped(reason="budget_exhausted")
            logger.info("autonomous loop stopped: budget_exhausted")
            _log_lifecycle_event(event="autonomous_loop_stopped", reason="budget_exhausted")
            return "budget_exhausted"
        except KeyboardInterrupt:
            agent.mark_stopped(reason="interrupted")
            logger.info("autonomous loop stopped: interrupted")
            _log_lifecycle_event(event="autonomous_loop_stopped", reason="interrupted")
            return "interrupted"
        except Exception as error:  # pragma: no cover - defensive loop guard
            failure_count += 1
            backoff_seconds = min(300, 2 ** min(failure_count, 8))
            logger.exception("autonomous cycle failure: %s", error)
            _log_lifecycle_event(
                event="autonomous_cycle_failed",
                error=str(error),
                backoff_seconds=backoff_seconds,
            )
            sleeper(backoff_seconds)

    agent.mark_stopped(reason="max_cycles_reached")
    _log_lifecycle_event(event="autonomous_loop_stopped", reason="max_cycles_reached")
    return "max_cycles_reached"


def _next_task_iteration(state: AutonomousState, goal: str, resumed_from_pending: bool) -> int:
    """Compute iteration index for the currently running goal."""
    if resumed_from_pending and state.current_task == goal and state.current_task_iteration > 0:
        return state.current_task_iteration
    if state.current_task == goal:
        return max(1, state.current_task_iteration + 1)
    return 1


def _task_base_elapsed_seconds(state: AutonomousState, goal: str, resumed_from_pending: bool) -> float:
    """Return elapsed time baseline to keep resumed work cumulative."""
    if resumed_from_pending and state.current_task == goal:
        return max(0.0, state.current_task_elapsed_seconds)
    if state.current_task == goal:
        return max(0.0, state.current_task_elapsed_seconds)
    return 0.0


def _extract_first_json_object(text: str) -> str:
    """Extract first JSON object substring from model output."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1]


def _parse_action(item: object) -> Optional[AgentAction]:
    """Parse a raw action dict into typed agent action."""
    if not isinstance(item, dict):
        return None

    action_type = str(item.get("type", "")).strip()
    if not action_type:
        return None

    if action_type == "run_command":
        raw_command = item.get("command", [])
        if not isinstance(raw_command, list) or not raw_command:
            return None
        command = [str(token) for token in raw_command if str(token).strip()]
        if not command:
            return None
        return AgentAction(action_type=action_type, command=command)

    if action_type == "search_web":
        query = str(item.get("query", "")).strip()
        if not query:
            return None
        return AgentAction(action_type=action_type, query=query)

    if action_type in {"write_file", "append_file"}:
        path = str(item.get("path", "")).strip()
        content = str(item.get("content", ""))
        if not path:
            return None
        return AgentAction(action_type=action_type, path=path, content=content)

    return None


def _dump_action(action: AgentAction) -> dict:
    """Serialize typed action for durable state persistence."""
    payload: dict = {"type": action.action_type}
    if action.command is not None:
        payload["command"] = list(action.command)
    if action.query:
        payload["query"] = action.query
    if action.path:
        payload["path"] = action.path
    if action.content:
        payload["content"] = action.content
    return payload


def _load_pending_actions(raw_actions: object) -> List[AgentAction]:
    """Deserialize pending action payloads from state file."""
    if not isinstance(raw_actions, list):
        return []

    parsed_actions: List[AgentAction] = []
    for raw_action in raw_actions:
        parsed = _parse_action(raw_action)
        if parsed is not None:
            parsed_actions.append(parsed)
    return parsed_actions


def _resolve_workspace_path(workspace_path: Path, relative_path: str) -> Optional[Path]:
    """Resolve and validate path to stay within workspace root."""
    root = workspace_path.resolve()
    candidate = (root / relative_path).resolve()

    root_text = str(root)
    candidate_text = str(candidate)
    if candidate_text == root_text or candidate_text.startswith(root_text + "/"):
        return candidate
    return None


# Emit lightweight lifecycle events from autonomous runtime internals.
def _log_lifecycle_event(event: str, **fields: object) -> None:
    """Write one lifecycle event to dedicated logger as JSON text."""
    payload = {
        "event": event,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    logging.getLogger("llm247.lifecycle").info(json.dumps(payload, ensure_ascii=False, sort_keys=True))

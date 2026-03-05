from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler

from llm247.ark_client import ArkModelClient, BudgetExhaustedError
from llm247.autonomous import (
    AutonomousAgent,
    AutonomousPlanner,
    AutonomousStateStore,
    CommandSafetyPolicy,
    SafeActionExecutor,
    WebSearchClient,
    run_autonomous_loop,
)
from llm247.config import WorkerConfig
from llm247.dashboard import serve_control_plane
from llm247.daemon import should_restart_child
from llm247.reports import ReportWriter
from llm247.runtime_codes import EXIT_BUDGET_EXHAUSTED, EXIT_INTERRUPTED, EXIT_RUNTIME_ERROR
from llm247.storage import TaskStateStore
from llm247.tasks import build_default_tasks
from llm247.token_usage import TokenUsageLogFilter
from llm247.worker import ContinuousWorker


# Configure console and daily-rotated lifecycle log handlers.
def configure_logging(log_path: str, retention_days: int = 30) -> None:
    """Configure root logging with daily rotation and retention."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    for existing_handler in list(logger.handlers):
        existing_handler.close()
        logger.removeHandler(existing_handler)

    file_handler = TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        interval=1,
        backupCount=retention_days,
        encoding="utf-8",
        utc=True,
    )
    token_filter = TokenUsageLogFilter()
    file_handler.addFilter(token_filter)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s "
            "token_cost=%(token_cost)s token_input_tokens=%(token_input_tokens)s "
            "token_output_tokens=%(token_output_tokens)s token_total_tokens=%(token_total_tokens)s "
            "token_calls=%(token_calls)s"
        )
    )

    stream_handler = logging.StreamHandler()
    stream_handler.addFilter(token_filter)
    stream_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s "
            "token_cost=%(token_cost)s token_input_tokens=%(token_input_tokens)s "
            "token_output_tokens=%(token_output_tokens)s token_total_tokens=%(token_total_tokens)s "
            "token_calls=%(token_calls)s"
        )
    )

    logger.handlers = [file_handler, stream_handler]


# Emit structured lifecycle event logs for traceability.
def log_lifecycle_event(event: str, **fields: object) -> None:
    """Log one structured lifecycle event as JSON payload."""
    payload = {
        "event": event,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    logging.getLogger("llm247.lifecycle").info(json.dumps(payload, ensure_ascii=False, sort_keys=True))


# Build legacy fixed-task worker for compatibility mode.
def build_legacy_worker(config: WorkerConfig) -> ContinuousWorker:
    """Create legacy periodic worker with predefined tasks."""
    model_client = ArkModelClient(api_key=config.api_key, base_url=config.base_url, model=config.model)
    state_store = TaskStateStore(config.state_path)
    report_writer = ReportWriter(config.report_dir)
    tasks = build_default_tasks()
    return ContinuousWorker(
        workspace_path=config.workspace_path,
        state_store=state_store,
        report_writer=report_writer,
        model_client=model_client,
        tasks=tasks,
    )


# Build autonomous goal-setting runtime components.
def build_autonomous_agent(config: WorkerConfig) -> AutonomousAgent:
    """Create autonomous agent that self-defines goals and actions."""
    model_client = ArkModelClient(api_key=config.api_key, base_url=config.base_url, model=config.model)
    planner = AutonomousPlanner(model_client=model_client, max_actions=config.autonomous_max_actions)
    executor = SafeActionExecutor(
        safety_policy=CommandSafetyPolicy(),
        web_search_client=WebSearchClient(result_limit=config.web_result_limit),
        command_timeout_seconds=config.command_timeout_seconds,
    )
    state_store = AutonomousStateStore(config.autonomous_state_path)
    report_writer = ReportWriter(config.report_dir)
    return AutonomousAgent(
        workspace_path=config.workspace_path,
        planner=planner,
        executor=executor,
        state_store=state_store,
        report_writer=report_writer,
    )


# Legacy loop: run fixed tasks forever.
def run_legacy_forever(worker: ContinuousWorker, poll_interval_seconds: int) -> str:
    """Run legacy scheduling loop forever with backoff on loop failures."""
    logger = logging.getLogger("llm247.legacy")
    failure_count = 0

    while True:
        try:
            log_lifecycle_event("legacy_cycle_started")
            now = datetime.now(timezone.utc)
            reports = worker.run_once(now=now)
            logger.info("legacy cycle complete: generated=%s", len(reports))
            log_lifecycle_event("legacy_cycle_completed", generated=len(reports))
            failure_count = 0
            time.sleep(poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("legacy loop interrupted by user")
            log_lifecycle_event("legacy_loop_interrupted")
            return "interrupted"
        except Exception as error:  # pragma: no cover - defensive loop guard
            failure_count += 1
            delay_seconds = min(300, 2 ** min(failure_count, 8))
            logger.exception("legacy loop failure: %s", error)
            log_lifecycle_event(
                "legacy_cycle_failed",
                error=str(error),
                backoff_seconds=delay_seconds,
            )
            time.sleep(delay_seconds)


# Execute one runtime child process lifecycle and map it to exit codes.
def run_runtime_child(config: WorkerConfig, mode: str, once: bool) -> int:
    """Run runtime in current process and return mapped exit code."""
    try:
        if mode == "legacy":
            worker = build_legacy_worker(config)
            if once:
                generated = worker.run_once(now=datetime.now(timezone.utc))
                for report_path in generated:
                    print(report_path)
                log_lifecycle_event("legacy_once_completed", generated=len(generated))
                return 0

            reason = run_legacy_forever(worker=worker, poll_interval_seconds=config.poll_interval_seconds)
            if reason == "interrupted":
                return EXIT_INTERRUPTED
            return 0

        agent = build_autonomous_agent(config)
        if once:
            report_path = agent.run_once(now=datetime.now(timezone.utc))
            print(report_path)
            log_lifecycle_event("autonomous_once_completed", report=str(report_path))
            return 0

        stop_reason = run_autonomous_loop(
            agent=agent,
            poll_interval_seconds=config.poll_interval_seconds,
        )
        log_lifecycle_event("autonomous_loop_stopped", reason=stop_reason)
        if stop_reason == "budget_exhausted":
            return EXIT_BUDGET_EXHAUSTED
        if stop_reason == "interrupted":
            return EXIT_INTERRUPTED
        return 0
    except BudgetExhaustedError:
        log_lifecycle_event("runtime_budget_exhausted")
        return EXIT_BUDGET_EXHAUSTED
    except KeyboardInterrupt:
        log_lifecycle_event("runtime_interrupted")
        return EXIT_INTERRUPTED
    except Exception as error:  # pragma: no cover - defensive runtime guard
        logging.getLogger("llm247.runtime").exception("runtime child crashed: %s", error)
        log_lifecycle_event("runtime_child_crashed", error=str(error))
        return EXIT_RUNTIME_ERROR


# Supervise child runtime and restart on unexpected crashes.
def run_daemon_supervisor(config: WorkerConfig, mode: str) -> int:
    """Run daemon supervisor that monitors and restarts child runtime process."""
    logger = logging.getLogger("llm247.daemon")
    restart_count = 0

    while True:
        command = [
            sys.executable,
            "-m",
            "llm247",
            "--child-process",
            "--mode",
            mode,
        ]
        log_lifecycle_event(
            "daemon_child_starting",
            command=command,
            restart_count=restart_count,
            cwd=str(config.workspace_path),
        )

        child = subprocess.Popen(
            command,
            cwd=str(config.workspace_path),
            env=os.environ.copy(),
        )

        try:
            child_exit_code = child.wait()
        except KeyboardInterrupt:
            logger.info("daemon interrupted by user, terminating child")
            log_lifecycle_event("daemon_interrupted", child_pid=child.pid)
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)
            return EXIT_INTERRUPTED

        log_lifecycle_event(
            "daemon_child_exited",
            child_pid=child.pid,
            exit_code=child_exit_code,
            restart_count=restart_count,
        )

        if not should_restart_child(
            child_exit_code=child_exit_code,
            restart_count=restart_count,
            max_restarts=config.daemon_max_restarts,
        ):
            logger.info("daemon stopping without restart: exit_code=%s", child_exit_code)
            log_lifecycle_event("daemon_stopped", exit_code=child_exit_code)
            return child_exit_code

        restart_count += 1
        logger.warning(
            "child crashed, restarting in %s seconds (restart_count=%s)",
            config.daemon_restart_delay_seconds,
            restart_count,
        )
        log_lifecycle_event(
            "daemon_restart_scheduled",
            delay_seconds=config.daemon_restart_delay_seconds,
            restart_count=restart_count,
        )
        time.sleep(config.daemon_restart_delay_seconds)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for run mode, one-shot behavior, and supervision."""
    parser = argparse.ArgumentParser(description="7x24 LLM autonomous worker")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    parser.add_argument(
        "--mode",
        choices=["autonomous", "legacy"],
        default=None,
        help="override RUN_MODE from environment",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="run a supervisor process that restarts child runtime on crash",
    )
    parser.add_argument("--ui", action="store_true", help="run task control-plane web UI only")
    parser.add_argument("--ui-host", default="127.0.0.1", help="control-plane listen host")
    parser.add_argument("--ui-port", type=int, default=8787, help="control-plane listen port")
    parser.add_argument("--child-process", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    """Program entry point for autonomous or legacy runtime modes."""
    args = parse_args()
    config = WorkerConfig.from_env()
    mode = args.mode or config.run_mode

    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    configure_logging(str(config.log_path), retention_days=config.log_retention_days)

    log_lifecycle_event(
        "runtime_started",
        pid=os.getpid(),
        mode=mode,
        daemon=args.daemon,
        once=args.once,
    )

    if args.ui:
        if args.daemon or args.once:
            logging.getLogger("llm247.dashboard").warning("--ui ignores runtime flags --daemon/--once")
        log_lifecycle_event(
            "control_plane_started",
            host=args.ui_host,
            port=args.ui_port,
        )
        serve_control_plane(
            workspace_path=config.workspace_path,
            autonomous_state_path=config.autonomous_state_path,
            legacy_state_path=config.state_path,
            host=args.ui_host,
            port=args.ui_port,
        )
        return 0

    if args.daemon and args.once:
        logging.getLogger("llm247.daemon").warning("--daemon with --once is ignored, running once directly")
        log_lifecycle_event("daemon_once_conflict", resolution="run_once_directly")
        return run_runtime_child(config=config, mode=mode, once=True)

    if args.daemon and not args.child_process:
        return run_daemon_supervisor(config=config, mode=mode)

    return run_runtime_child(config=config, mode=mode, once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())

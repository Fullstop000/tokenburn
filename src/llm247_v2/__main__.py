from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def _resolve_bound_model(model_store, binding_point: str):
    """Resolve one registered model for a binding point, or return None."""
    binding = model_store.get_binding(binding_point)
    if not binding:
        return None
    return model_store.get_model(binding.model_id)


def _bootstrap_status(model_store) -> dict:
    """Summarize whether runtime prerequisites are satisfied."""
    ready = model_store.get_default_model() is not None
    missing = [] if ready else ["default_llm"]
    return {
        "ready": ready,
        "requires_setup": not ready,
        "missing": missing,
        "recommended_tab": "models",
        "message": (
            "Register at least one llm model in the Models page to finish initialization."
            if not ready
            else "Runtime prerequisites satisfied."
        ),
    }


def _load_env() -> None:
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path, override=False)
    except ImportError:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


def _configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        h.close()
        root.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    fh = TimedRotatingFileHandler(str(log_path), when="midnight", backupCount=30, utc=True, encoding="utf-8")
    fh.setFormatter(fmt)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)

    root.handlers = [fh, sh]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sprout Agent V2 — Autonomous 24/7 engineering agent")
    p.add_argument("--once", action="store_true", help="Run one cycle and exit")
    p.add_argument("--max-cycles", type=int, default=None, help="Max number of cycles before stopping")
    p.add_argument("--ui", action="store_true", help="Run dashboard UI only")
    p.add_argument("--ui-host", default="127.0.0.1", help="Dashboard listen host")
    p.add_argument("--ui-port", type=int, default=8787, help="Dashboard listen port")
    p.add_argument("--with-ui", action="store_true", help="Run agent + dashboard together")
    p.add_argument("--workspace", default=None, help="Override workspace path")
    p.add_argument("--branch-prefix", default="agent", help="Git branch prefix (default: agent)")
    return p.parse_args()


def main() -> int:
    _load_env()
    args = parse_args()

    workspace = Path(args.workspace or os.getenv("WORKSPACE_PATH", os.getcwd())).resolve()
    state_dir = workspace / ".llm247_v2"
    db_path = state_dir / "tasks.db"
    models_db_path = state_dir / "models.db"
    directive_path = state_dir / "directive.json"
    constitution_path = state_dir / "constitution.md"
    exploration_map_path = state_dir / "exploration_map.json"
    interest_profile_path = state_dir / "interest_profile.json"
    log_path = state_dir / "agent.log"
    poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "120"))
    command_timeout = int(os.getenv("COMMAND_TIMEOUT_SECONDS", "60"))

    _configure_logging(log_path)
    logger = logging.getLogger("llm247_v2")
    logger.info("Sprout Agent V2 starting workspace=%s", workspace)

    from llm247_v2.storage.store import TaskStore
    from llm247_v2.storage.model_registry import ModelRegistryStore
    store = TaskStore(db_path)
    model_store = ModelRegistryStore(models_db_path)
    bootstrap = _bootstrap_status(model_store)

    if args.ui:
        from llm247_v2.dashboard.server import serve_dashboard
        from llm247_v2.storage.experience import ExperienceStore
        from llm247_v2.storage.thread_store import ThreadStore as _ThreadStore

        exp_store = ExperienceStore(state_dir / "experience.db")
        ui_thread_store = _ThreadStore(state_dir / "threads.db")
        try:
            serve_dashboard(
                store,
                directive_path,
                host=args.ui_host,
                port=args.ui_port,
                state_dir=state_dir,
                experience_store=exp_store,
                model_store=model_store,
                bootstrap_status_provider=lambda: _bootstrap_status(model_store),
                thread_store=ui_thread_store,
            )
            return 0
        finally:
            exp_store.close()
            ui_thread_store.close()
            model_store.close()
            store.close()

    from llm247_v2.llm.client import ArkLLMClient, BudgetExhaustedError, LLMAuditLogger, RoutedLLMClient, TokenTracker
    from llm247_v2.agent import AutonomousAgentV2, GracefulShutdown, run_agent_loop
    from llm247_v2.storage.experience import ExperienceStore
    from llm247_v2.observability.observer import create_default_observer
    from llm247_v2.dashboard.server import serve_dashboard

    exp_store = ExperienceStore(state_dir / "experience.db")

    if args.with_ui or bootstrap["requires_setup"]:
        ui_thread = threading.Thread(
            target=serve_dashboard,
            args=(store, directive_path, args.ui_host, args.ui_port),
            kwargs={
                "state_dir": state_dir,
                "experience_store": exp_store,
                "model_store": model_store,
                "bootstrap_status_provider": lambda: _bootstrap_status(model_store),
                "thread_store": thread_store,
            },
            daemon=True,
        )
        ui_thread.start()
        logger.info("Dashboard started on http://%s:%d", args.ui_host, args.ui_port)

    if bootstrap["requires_setup"]:
        logger.warning("Runtime prerequisites missing: %s", ", ".join(bootstrap["missing"]))
        logger.warning("Entering setup mode. Open http://%s:%d and complete initialization.", args.ui_host, args.ui_port)
        try:
            while True:
                bootstrap = _bootstrap_status(model_store)
                if bootstrap["ready"]:
                    logger.info("Initialization completed; resuming agent startup")
                    break
                time.sleep(1.0)
        except KeyboardInterrupt:
            exp_store.close()
            model_store.close()
            store.close()
            return 32

    default_registered_model = model_store.get_default_model()
    if default_registered_model is None:
        exp_store.close()
        model_store.close()
        store.close()
        print("ERROR: initialization incomplete, no default llm registered", file=sys.stderr)
        return 1

    audit_logger = LLMAuditLogger(state_dir / "llm_audit.jsonl")
    shared_tracker = TokenTracker()
    default_llm = ArkLLMClient(
        api_key=default_registered_model.api_key,
        base_url=default_registered_model.base_url,
        model=default_registered_model.model_name,
        audit_logger=audit_logger,
        tracker=shared_tracker,
    )
    llm = RoutedLLMClient(
        default_client=default_llm,
        binding_resolver=lambda binding_point: _resolve_bound_model(model_store, binding_point),
        client_factory=lambda registered_model: ArkLLMClient(
            api_key=registered_model.api_key,
            base_url=registered_model.base_url,
            model=registered_model.model_name,
            audit_logger=audit_logger,
            tracker=shared_tracker,
        ),
    )
    observer = create_default_observer(state_dir, store=store, console=True)
    shutdown_event = threading.Event()

    from llm247_v2.storage.thread_store import ThreadStore
    thread_store = ThreadStore(state_dir / "threads.db")

    agent = AutonomousAgentV2(
        workspace=workspace,
        store=store,
        llm=llm,
        directive_path=directive_path,
        constitution_path=constitution_path,
        exploration_map_path=exploration_map_path,
        experience_store=exp_store,
        observer=observer,
        branch_prefix=args.branch_prefix,
        interest_profile_path=interest_profile_path,
        shutdown_event=shutdown_event,
        thread_store=thread_store,
    )

    def _handle_signal(signum: int, _frame) -> None:
        sig_name = signal.Signals(signum).name
        if shutdown_event.is_set():
            logger.warning("Received second %s — forcing immediate exit", sig_name)
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
            return
        logger.info("Received %s — initiating graceful shutdown (send again to force)", sig_name)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        if args.once:
            summary = agent.run_cycle()
            logger.info("Single cycle result: %s", summary)
            return 0

        def _interruptible_sleep(seconds: float) -> None:
            """Sleep that can be interrupted by shutdown_event."""
            shutdown_event.wait(timeout=seconds)
            if shutdown_event.is_set():
                raise KeyboardInterrupt("graceful shutdown")

        reason = run_agent_loop(
            agent=agent,
            poll_interval=poll_interval,
            max_cycles=args.max_cycles,
            sleeper=_interruptible_sleep,
        )
        logger.info("Agent loop stopped: %s", reason)

        if reason == "budget_exhausted":
            return 31
        if reason == "interrupted":
            return 32
        return 0

    except BudgetExhaustedError:
        logger.info("Budget exhausted")
        return 31
    except (KeyboardInterrupt, GracefulShutdown):
        logger.info("Interrupted by user")
        return 32
    except Exception:
        logger.exception("Agent crashed")
        return 70
    finally:
        observer.close()
        exp_store.close()
        audit_logger.close()
        thread_store.close()
        model_store.close()
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

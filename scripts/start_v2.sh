#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

usage() {
    cat <<'EOF'
TokenBurn Agent V2 — Autonomous 24/7 Engineering Agent

Usage:
  ./scripts/start_v2.sh agent        Run agent loop (24/7 autonomous mode)
  ./scripts/start_v2.sh ui           Run dashboard UI only
  ./scripts/start_v2.sh both         Run agent + dashboard together
  ./scripts/start_v2.sh once         Run a single agent cycle
  ./scripts/start_v2.sh test         Run V2 test suite

Options (via environment):
  ARK_API_KEY              API key for LLM (required for agent)
  ARK_MODEL                Model identifier (required for agent)
  ARK_BASE_URL             API endpoint (default: Ark Beijing)
  WORKSPACE_PATH           Workspace directory (default: current dir)
  POLL_INTERVAL_SECONDS    Seconds between cycles (default: 120)
  COMMAND_TIMEOUT_SECONDS  Command execution timeout (default: 60)

Control:
  Edit .llm247_v2/directive.json to control agent behavior, or
  use the dashboard UI at http://127.0.0.1:8787
EOF
}

case "${1:-help}" in
    agent)
        echo "Starting TokenBurn Agent V2..."
        PYTHONPATH=src exec python3 -m llm247_v2
        ;;
    ui)
        echo "Starting Dashboard UI on http://127.0.0.1:${UI_PORT:-8787}"
        PYTHONPATH=src exec python3 -m llm247_v2 --ui --ui-port "${UI_PORT:-8787}"
        ;;
    both)
        echo "Starting Agent + Dashboard..."
        PYTHONPATH=src exec python3 -m llm247_v2 --with-ui --ui-port "${UI_PORT:-8787}"
        ;;
    once)
        echo "Running single agent cycle..."
        PYTHONPATH=src exec python3 -m llm247_v2 --once
        ;;
    test)
        echo "Running V2 test suite..."
        PYTHONPATH=src python3 -m unittest discover -s tests -p "test_v2_*.py" -v
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo "Unknown command: $1"
        usage
        exit 1
        ;;
esac

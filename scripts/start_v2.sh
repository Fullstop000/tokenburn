#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_DIR/frontend"
FRONTEND_DIST_DIR="$FRONTEND_DIR/dist"
NPM_CACHE_DIR="${NPM_CACHE_DIR:-/tmp/.npm-cache}"

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
  FORCE_FRONTEND_BUILD     Force rebuilding frontend before ui/both (1=true)
  SKIP_FRONTEND_BUILD      Skip auto frontend build check for ui/both (1=true)
  NPM_CACHE_DIR            npm cache path (default: /tmp/.npm-cache)

Control:
  Edit .llm247_v2/directive.json to control agent behavior, or
  use the dashboard UI at http://127.0.0.1:8787
EOF
}

# Ensure dashboard frontend build artifacts exist before starting UI.
ensure_frontend_assets() {
    if [[ "${SKIP_FRONTEND_BUILD:-0}" == "1" ]]; then
        echo "Skipping frontend build check (SKIP_FRONTEND_BUILD=1)"
        return 0
    fi

    if [[ ! -d "$FRONTEND_DIR" || ! -f "$FRONTEND_DIR/package.json" ]]; then
        echo "error: frontend project not found at $FRONTEND_DIR" >&2
        exit 1
    fi

    if [[ "${FORCE_FRONTEND_BUILD:-0}" != "1" && -f "$FRONTEND_DIST_DIR/index.html" && -f "$FRONTEND_DIST_DIR/assets/dashboard.js" ]]; then
        echo "Using existing dashboard frontend build at $FRONTEND_DIST_DIR"
        return 0
    fi

    if ! command -v npm >/dev/null 2>&1; then
        echo "error: npm is required to build dashboard frontend (ui/both mode)" >&2
        exit 1
    fi

    echo "Building dashboard frontend..."
    (
        cd "$FRONTEND_DIR"
        if [[ ! -d node_modules ]]; then
            echo "Installing frontend dependencies..."
            npm_config_cache="$NPM_CACHE_DIR" npm install
        fi
        npm_config_cache="$NPM_CACHE_DIR" npm run build
    )
}

case "${1:-help}" in
    agent)
        echo "Starting TokenBurn Agent V2..."
        PYTHONPATH=src exec python3 -m llm247_v2
        ;;
    ui)
        ensure_frontend_assets
        echo "Starting Dashboard UI on http://127.0.0.1:${UI_PORT:-8787}"
        PYTHONPATH=src exec python3 -m llm247_v2 --ui --ui-port "${UI_PORT:-8787}"
        ;;
    both)
        ensure_frontend_assets
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

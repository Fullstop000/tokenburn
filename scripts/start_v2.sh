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
Sprout Agent V2 — Autonomous 24/7 Engineering Agent

Usage:
  ./scripts/start_v2.sh agent        Run agent loop (24/7 autonomous mode)
  ./scripts/start_v2.sh ui           Run dashboard UI only          [production]
  ./scripts/start_v2.sh both         Run agent + dashboard          [production]
  ./scripts/start_v2.sh ui-dev       Run dashboard UI with hot reload [dev]
  ./scripts/start_v2.sh both-dev     Run agent + dashboard with hot reload [dev]
  ./scripts/start_v2.sh once         Run a single agent cycle
  ./scripts/start_v2.sh test         Run V2 test suite

Production vs Dev:
  Production (ui / both):
    Frontend is pre-built and served as static files by the Python backend.
    Access the dashboard at http://127.0.0.1:8787

  Dev (ui-dev / both-dev):
    Vite dev server runs alongside the Python API backend.
    Frontend hot-reloads on every code change.
    Access the dashboard at http://127.0.0.1:5173  (Vite)
    Python API runs at   http://127.0.0.1:8787  (proxied automatically)

Options (via environment):
  ARK_API_KEY              API key for LLM (required for agent)
  ARK_MODEL                Model identifier (required for agent)
  ARK_BASE_URL             API endpoint (default: Ark Beijing)
  WORKSPACE_PATH           Workspace directory (default: current dir)
  POLL_INTERVAL_SECONDS    Seconds between cycles (default: 120)
  COMMAND_TIMEOUT_SECONDS  Command execution timeout (default: 60)
  UI_PORT                  Python backend port (default: 8787)
  VITE_PORT                Vite dev server port (default: 5173)
  FORCE_FRONTEND_BUILD     Force rebuilding frontend before ui/both (1=true)
  SKIP_FRONTEND_BUILD      Skip auto frontend build check for ui/both (1=true)
  NPM_CACHE_DIR            npm cache path (default: /tmp/.npm-cache)

Control:
  Edit .llm247_v2/directive.json to control agent behavior, or
  use the dashboard UI at http://127.0.0.1:${UI_PORT:-8787}
EOF
}

# ── Helpers ──────────────────────────────────────────────────────────

require_npm() {
    if ! command -v npm >/dev/null 2>&1; then
        echo "error: npm is required for this command" >&2
        exit 1
    fi
}

require_frontend_dir() {
    if [[ ! -d "$FRONTEND_DIR" || ! -f "$FRONTEND_DIR/package.json" ]]; then
        echo "error: frontend project not found at $FRONTEND_DIR" >&2
        exit 1
    fi
}

ensure_node_modules() {
    if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
        echo "Installing frontend dependencies..."
        (cd "$FRONTEND_DIR" && npm_config_cache="$NPM_CACHE_DIR" npm install)
    fi
}

# Ensure production build artifacts exist.
ensure_frontend_assets() {
    if [[ "${SKIP_FRONTEND_BUILD:-0}" == "1" ]]; then
        echo "Skipping frontend build check (SKIP_FRONTEND_BUILD=1)"
        return 0
    fi

    require_npm
    require_frontend_dir

    if [[ "${FORCE_FRONTEND_BUILD:-0}" != "1" \
       && -f "$FRONTEND_DIST_DIR/index.html" \
       && -f "$FRONTEND_DIST_DIR/assets/dashboard.js" ]]; then
        echo "Using existing frontend build at $FRONTEND_DIST_DIR"
        return 0
    fi

    echo "Building frontend..."
    (
        cd "$FRONTEND_DIR"
        ensure_node_modules
        npm_config_cache="$NPM_CACHE_DIR" npm run build
    )
}

# Start Vite dev server in background; store PID in VITE_PID.
start_vite_dev() {
    require_npm
    require_frontend_dir
    ensure_node_modules

    local vite_port="${VITE_PORT:-5173}"
    local api_port="${UI_PORT:-8787}"

    echo "Starting Vite dev server on http://127.0.0.1:${vite_port}  (API proxy → :${api_port})"
    (
        cd "$FRONTEND_DIR"
        VITE_PORT="$vite_port" VITE_API_PORT="$api_port" \
            npm_config_cache="$NPM_CACHE_DIR" npm run dev
    ) &
    VITE_PID=$!
}

# Kill Vite dev server on exit.
cleanup_vite() {
    if [[ -n "${VITE_PID:-}" ]] && kill -0 "$VITE_PID" 2>/dev/null; then
        echo "Stopping Vite dev server (pid $VITE_PID)..."
        kill "$VITE_PID" 2>/dev/null || true
    fi
}

# ── Commands ─────────────────────────────────────────────────────────

case "${1:-help}" in
    agent)
        echo "Starting Sprout Agent V2..."
        PYTHONPATH=src exec python3 -m llm247_v2
        ;;

    ui)
        ensure_frontend_assets
        echo "Starting Dashboard UI (production) on http://127.0.0.1:${UI_PORT:-8787}"
        PYTHONPATH=src exec python3 -m llm247_v2 --ui --ui-port "${UI_PORT:-8787}"
        ;;

    both)
        ensure_frontend_assets
        echo "Starting Agent + Dashboard (production) on http://127.0.0.1:${UI_PORT:-8787}"
        PYTHONPATH=src exec python3 -m llm247_v2 --with-ui --ui-port "${UI_PORT:-8787}"
        ;;

    ui-dev)
        echo "=== Dev mode: frontend hot reload enabled ==="
        VITE_PID=""
        trap cleanup_vite EXIT INT TERM

        # Start Python API backend (skips frontend serving; Vite handles that)
        echo "Starting Python API backend on http://127.0.0.1:${UI_PORT:-8787}"
        PYTHONPATH=src python3 -m llm247_v2 --ui --ui-port "${UI_PORT:-8787}" &
        BACKEND_PID=$!

        # Give backend a moment to bind the port
        sleep 1

        start_vite_dev

        echo ""
        echo "  Dashboard (hot reload):  http://127.0.0.1:${VITE_PORT:-5173}"
        echo "  API backend:             http://127.0.0.1:${UI_PORT:-8787}"
        echo "  Press Ctrl+C to stop both."
        echo ""

        # Wait for either process to exit
        wait "$BACKEND_PID" "$VITE_PID"
        ;;

    both-dev)
        echo "=== Dev mode: agent + frontend hot reload enabled ==="
        VITE_PID=""
        trap cleanup_vite EXIT INT TERM

        # Start agent + API backend
        echo "Starting Agent + API backend on http://127.0.0.1:${UI_PORT:-8787}"
        PYTHONPATH=src python3 -m llm247_v2 --with-ui --ui-port "${UI_PORT:-8787}" &
        BACKEND_PID=$!

        sleep 1

        start_vite_dev

        echo ""
        echo "  Dashboard (hot reload):  http://127.0.0.1:${VITE_PORT:-5173}"
        echo "  API backend:             http://127.0.0.1:${UI_PORT:-8787}"
        echo "  Press Ctrl+C to stop all."
        echo ""

        wait "$BACKEND_PID" "$VITE_PID"
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

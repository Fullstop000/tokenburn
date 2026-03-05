#!/usr/bin/env bash
set -euo pipefail

# Resolve repository root from script location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/start.sh [worker|ui|both] [extra llm247 args...]

Modes:
  worker   Start autonomous runtime loop directly. (default)
  ui       Start control-plane web UI only.
  both     Start worker in background and UI in foreground.

Environment:
  Loads .env automatically when present.
  Required: ARK_API_KEY, ARK_MODEL
  Optional: UI_HOST (default 127.0.0.1), UI_PORT (default 8787)
EOF
}

# Load .env into current shell process for llm247 runtime.
load_env() {
  if [[ -f ".env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source ".env"
    set +a
  fi
}

# Fail fast for missing required model credentials.
validate_env() {
  if [[ -z "${ARK_API_KEY:-}" ]]; then
    echo "error: ARK_API_KEY is required (set in .env or environment)." >&2
    exit 1
  fi
  if [[ -z "${ARK_MODEL:-}" ]]; then
    echo "error: ARK_MODEL is required (set in .env or environment)." >&2
    exit 1
  fi
}

run_worker() {
  PYTHONPATH=src python3 -m llm247 "$@"
}

run_ui() {
  local host="${UI_HOST:-127.0.0.1}"
  local port="${UI_PORT:-8787}"
  PYTHONPATH=src python3 -m llm247 --ui --ui-host "${host}" --ui-port "${port}" "$@"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

MODE="${1:-worker}"
if [[ "${#}" -gt 0 ]]; then
  shift
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 not found in PATH." >&2
  exit 1
fi

load_env
validate_env

case "${MODE}" in
  worker)
    run_worker "$@"
    ;;
  ui)
    run_ui "$@"
    ;;
  both)
    run_worker "$@" &
    WORKER_PID=$!
    trap 'kill "${WORKER_PID}" 2>/dev/null || true' EXIT
    run_ui
    ;;
  *)
    echo "error: unknown mode '${MODE}'." >&2
    usage
    exit 1
    ;;
esac

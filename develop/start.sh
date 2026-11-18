#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# start.sh — Launch the EMFI Develop service (backend + frontend)
#
# Starts the FastAPI backend on port 8002 and the SvelteKit
# frontend dev server on port 5173.  In production mode
# (--prod), builds the frontend once and serves it via FastAPI
# StaticFiles — no separate frontend process needed.
#
# Usage:
#   ./start.sh              # dev mode: backend + frontend hot-reload
#   ./start.sh --prod       # build frontend, serve from FastAPI only
#   ./start.sh --debug      # DEBUG log level
#   ./start.sh --port 9002  # custom backend port
#
# Environment overrides:
#   EMFI_LOG_LEVEL     INFO | DEBUG | WARNING  (default: INFO)
#   EMFI_LOG_DIR       path to log directory   (default: ./logs)
#   EMFI_PROJECTS_ROOT path to projects        (default: ~/emfi-projects)
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Defaults ────────────────────────────────────────────────
PORT=8002
HOST="0.0.0.0"
LOG_LEVEL="${EMFI_LOG_LEVEL:-INFO}"
LOG_DIR="${EMFI_LOG_DIR:-$SCRIPT_DIR/logs}"
RELOAD=""
PROD=false

# ── Parse arguments ─────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --debug)
            LOG_LEVEL="DEBUG"
            shift ;;
        --port)
            PORT="$2"
            shift 2 ;;
        --reload)
            RELOAD="--reload"
            shift ;;
        --prod)
            PROD=true
            shift ;;
        --help|-h)
            head -20 "$0" | grep '^#' | sed 's/^# \?//'
            exit 0 ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1 ;;
    esac
done

export EMFI_LOG_LEVEL="$LOG_LEVEL"
export EMFI_LOG_DIR="$LOG_DIR"

PROJECTS_PATH="${EMFI_PROJECTS_ROOT:-$HOME/emfi-projects}"

# ── Prepare log directory and session log file ──────────────
mkdir -p "$LOG_DIR"
SESSION_LOG="$LOG_DIR/develop-$(date +%Y%m%d-%H%M%S).log"

ln -sfn "$(basename "$SESSION_LOG")" "$LOG_DIR/latest.log"

# ── venv discovery / creation ───────────────────────────────
LOCAL_VENV="$SCRIPT_DIR/.venv"
SHARED_VENV="$SCRIPT_DIR/../.venv"

if [ -n "${VIRTUAL_ENV:-}" ]; then
    :
elif [ -d "$LOCAL_VENV" ]; then
    source "$LOCAL_VENV/bin/activate"
elif [ -d "$SHARED_VENV" ]; then
    source "$SHARED_VENV/bin/activate"
else
    echo "Creating virtual environment at $LOCAL_VENV ..."
    python3 -m venv "$LOCAL_VENV"
    source "$LOCAL_VENV/bin/activate"
    pip install --quiet --upgrade pip
    pip install --quiet -e ../protocol -e ".[extras,dev]"
    echo "Virtual environment ready."
fi

export PATH="$HOME/.local/bin:$PATH"

# ── Ensure Node.js is available (Volta, nvm, or system) ────
if ! command -v node &>/dev/null; then
    for candidate in "$HOME/.volta/bin" "$HOME/.nvm/versions/node"/*/bin; do
        if [ -x "$candidate/node" ]; then
            export PATH="$candidate:$PATH"
            break
        fi
    done
fi

if ! command -v node &>/dev/null; then
    echo "WARNING: Node.js not found — frontend will not start." >&2
    echo "         Install via: volta install node  (or nvm install --lts)" >&2
    PROD=true  # fall back to backend-only mode
fi

# ── Frontend npm install if needed ──────────────────────────
FRONTEND_DIR="$SCRIPT_DIR/frontend"
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "Installing frontend dependencies..."
    (cd "$FRONTEND_DIR" && npm install --silent)
fi

# ── Production mode: build frontend, serve from FastAPI ─────
if $PROD; then
    echo "Building frontend for production..."
    (cd "$FRONTEND_DIR" && npx svelte-kit sync && npm run build)
    echo ""

    cat <<EOF
  EMFI Develop — production mode
  ──────────────────────────────
  Backend:    http://localhost:$PORT
  Frontend:   served from FastAPI (built into frontend/build/)
  Log level:  $LOG_LEVEL
  Log file:   $SESSION_LOG
  Projects:   $PROJECTS_PATH

  Ctrl-C to stop.

EOF

    exec uvicorn develop.main:app \
        --host "$HOST" \
        --port "$PORT" \
        --log-level "$(echo "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')" \
        2>&1 | tee -a "$SESSION_LOG"
fi

# ── Dev mode: start both backend and frontend ───────────────
PIDS=()

cleanup() {
    echo ""
    echo "Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    wait 2>/dev/null
    echo "Stopped."
}
trap cleanup EXIT INT TERM

cat <<EOF

  EMFI Develop — dev mode
  ───────────────────────
  Backend:    http://localhost:$PORT   (API + WebSocket)
  Frontend:   http://localhost:5173    (hot-reload UI)
  Log level:  $LOG_LEVEL
  Log file:   $SESSION_LOG
  Projects:   $PROJECTS_PATH
  venv:       ${VIRTUAL_ENV:-<none>}

  Open http://localhost:5173 in your browser.
  Ctrl-C to stop both.

EOF

# Start backend
uvicorn develop.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level "$(echo "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')" \
    $RELOAD \
    2>&1 | tee -a "$SESSION_LOG" &
PIDS+=($!)

# Start frontend dev server
(cd "$FRONTEND_DIR" && npx svelte-kit sync && npm run dev -- --host 2>&1 | tee -a "$SESSION_LOG") &
PIDS+=($!)

# Wait for either to exit
wait -n "${PIDS[@]}" 2>/dev/null

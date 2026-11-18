#!/usr/bin/env bash
# start.sh — Start the EMFI Control service with logging to console and file.
#
# Usage:
#   ./start.sh              # normal start
#   ./start.sh --reload     # with auto-reload for development
#   ./start.sh --debug      # verbose (DEBUG-level) logging
#
# Logs are written to:
#   Console (stdout) — for real-time monitoring
#   ~/.local/share/emfi-control/logs/control.log — rotating, 10MB × 5 backups
#
# Override log location:
#   CONTROL_LOG_DIR=/path/to/logs ./start.sh
#
# Environment variables (all optional):
#   CONTROL_HOST       bind address   (default: 0.0.0.0)
#   CONTROL_PORT       bind port      (default: 8001)
#   CONTROL_LOG_DIR    log directory   (default: ~/.local/share/emfi-control/logs)
#   CONTROL_CONFIG     config path     (default: ~/.config/emfi-control/config.json)
#   CONTROL_DATA_DIR   sessions dir    (default: ~/.local/share/emfi-control/sessions)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------- defaults ----------
HOST="${CONTROL_HOST:-0.0.0.0}"
PORT="${CONTROL_PORT:-8001}"
LOG_DIR="${CONTROL_LOG_DIR:-${XDG_STATE_HOME:-$HOME/.local/share}/emfi-control/logs}"
RELOAD=""
LOG_LEVEL="info"

# ---------- parse flags ----------
for arg in "$@"; do
    case "$arg" in
        --reload)  RELOAD="--reload" ;;
        --debug)   LOG_LEVEL="debug" ;;
        --help|-h)
            head -18 "$0" | tail -16 | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown flag: $arg (try --help)" >&2
            exit 1
            ;;
    esac
done

# ---------- ensure log dir exists ----------
mkdir -p "$LOG_DIR"

# ---------- venv discovery / creation ----------
# Prefer (in order): caller-activated venv, local control/.venv,
# shared ../.venv, then create control/.venv as a last resort.
# The shared ../.venv is the canonical place hardware libs live
# (FaultyCat host tools) — picking it up here
# avoids needing to install them in two places.
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
    pip install --quiet -e ../protocol -e ".[dev]" -e ../../faultycat-tools
    echo "Virtual environment ready."
fi

# ---------- banner ----------
echo "========================================"
echo "  EMFI Control Service"
echo "  http://${HOST}:${PORT}/docs"
echo "  Log file: ${LOG_DIR}/control.log"
echo "  Log level: ${LOG_LEVEL}"
echo "  PID: $$"
echo "========================================"
echo ""

# ---------- export for main.py ----------
export CONTROL_HOST="$HOST"
export CONTROL_PORT="$PORT"
export CONTROL_LOG_DIR="$LOG_DIR"

# ---------- run ----------
exec uvicorn control.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level "$LOG_LEVEL" \
    $RELOAD

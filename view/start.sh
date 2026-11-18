#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-dev}"
PORT="${2:-8003}"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/view-$(date +%Y%m%d-%H%M%S).log"

# ── helpers ──────────────────────────────────────────────────────────────────

cleanup() {
    echo ""
    echo "[$(date -Iseconds)] Shutting down View (pid $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    echo "[$(date -Iseconds)] View stopped. Log saved to $LOGFILE"
}

log_header() {
    {
        echo "================================================================"
        echo "  EMFI View — $MODE mode"
        echo "  Started: $(date -Iseconds)"
        echo "  Port:    $PORT"
        echo "  PID:     $$"
        echo "  Node:    $(node --version 2>/dev/null || echo 'not found')"
        echo "  npm:     $(npm --version 2>/dev/null || echo 'not found')"
        echo "  Log:     $LOGFILE"
        echo "================================================================"
        echo ""
    }
}

# ── preflight checks ────────────────────────────────────────────────────────

if ! command -v node &>/dev/null; then
    echo "ERROR: node not found. Install Node.js (v18+) or activate Volta."
    exit 1
fi

if [ ! -d "$SCRIPT_DIR/node_modules" ]; then
    echo "[$(date -Iseconds)] node_modules missing — running npm install..."
    npm install 2>&1 | tee -a "$LOGFILE"
    echo ""
fi

# ── start ────────────────────────────────────────────────────────────────────

log_header | tee "$LOGFILE"

trap cleanup EXIT INT TERM

case "$MODE" in
    dev)
        echo "[$(date -Iseconds)] Starting Vite dev server on :$PORT ..."
        npx vite dev --port "$PORT" 2>&1 | tee -a "$LOGFILE" &
        SERVER_PID=$!
        ;;
    preview)
        echo "[$(date -Iseconds)] Building for production..."
        npm run build 2>&1 | tee -a "$LOGFILE"
        echo "[$(date -Iseconds)] Starting preview server on :$PORT ..."
        npx vite preview --port "$PORT" 2>&1 | tee -a "$LOGFILE" &
        SERVER_PID=$!
        ;;
    *)
        echo "Usage: $0 [dev|preview] [port]"
        echo "  dev      Hot-reload dev server (default)"
        echo "  preview  Production build + static preview"
        exit 1
        ;;
esac

echo "[$(date -Iseconds)] View running (pid $SERVER_PID). Press Ctrl+C to stop."
echo ""
wait "$SERVER_PID"

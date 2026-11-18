#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/uvicorn ]]; then
  echo 'Install dependencies first; see README.md.' >&2
  exit 1
fi
if ! command -v npm >/dev/null && [[ -x .tools/node/bin/npm ]]; then
  export PATH="$PWD/.tools/node/bin:$PATH"
fi
if ! command -v npm >/dev/null; then
  echo 'Node.js and npm are required; see README.md.' >&2
  exit 1
fi
cleanup() {
  trap - EXIT INT TERM
  kill "${pids[@]}" 2>/dev/null || true
  wait "${pids[@]}" 2>/dev/null || true
}
pids=()
trap cleanup EXIT INT TERM
.venv/bin/uvicorn control.main:app --host 127.0.0.1 --port 8001 &
pids+=("$!")
.venv/bin/uvicorn develop.main:app --host 127.0.0.1 --port 8002 &
pids+=("$!")
(cd view && npm run dev -- --host 127.0.0.1) &
pids+=("$!")
echo 'Dashboard: http://127.0.0.1:8003/'
wait -n "${pids[@]}"

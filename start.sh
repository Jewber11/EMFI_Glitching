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
(cd develop/frontend && DEVELOP_BASE_PATH=/develop npm run build)
(cd view && npm run build)
echo 'Dashboard: http://127.0.0.1:8003/'
exec .venv/bin/uvicorn emfi_app:app --host 127.0.0.1 --port 8003

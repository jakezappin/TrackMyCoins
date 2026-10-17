#!/usr/bin/env bash
# Start the backend (port 8000) and frontend (port 5173). Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$PWD/.tools/node/bin:$PATH"

(cd backend && .venv/bin/alembic upgrade head)

(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000) &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
(cd frontend && npm run dev)

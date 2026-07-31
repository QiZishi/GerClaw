#!/bin/sh
set -eu

: "${GERCLAW_DATABASE_URL:?GERCLAW_DATABASE_URL must point to an external PostgreSQL instance}"
: "${GERCLAW_REDIS_URL:?GERCLAW_REDIS_URL must point to an external Redis instance}"
: "${GERCLAW_QDRANT_URL:?GERCLAW_QDRANT_URL must point to an external Qdrant instance}"

cd /app/api
alembic upgrade head
uvicorn gerclaw_api.main:app --host 0.0.0.0 --port 8000 &
api_pid=$!

cleanup() {
    kill "$api_pid" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

cd /app/web
exec node server.js
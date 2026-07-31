#!/bin/sh
set -eu

runtime_root="${GERCLAW_INTERNAL_DATA_DIR:-/app/workspaces/gerclaw-services}"
if ! mkdir -p "$runtime_root" 2>/dev/null; then
    runtime_root="/app/workspaces/gerclaw-services"
    mkdir -p "$runtime_root"
fi

echo "[GerClaw] internal service data root: $runtime_root"

umask 077

read_or_create_secret() {
    secret_file="$1"
    if [ ! -s "$secret_file" ]; then
        python -c 'import secrets; print(secrets.token_hex(32), end="")' >"$secret_file"
    fi
    cat "$secret_file"
}

postgres_dir="$runtime_root/postgres"
redis_dir="$runtime_root/redis"
qdrant_dir="$runtime_root/qdrant"
mkdir -p "$postgres_dir" "$redis_dir" "$qdrant_dir" "$runtime_root/secrets"

postgres_password="${GERCLAW_INTERNAL_POSTGRES_PASSWORD:-}"
if [ -z "$postgres_password" ]; then
    postgres_password="$(read_or_create_secret "$runtime_root/secrets/postgres.password")"
fi

redis_password="${GERCLAW_INTERNAL_REDIS_PASSWORD:-}"
if [ -z "$redis_password" ]; then
    redis_password="$(read_or_create_secret "$runtime_root/secrets/redis.password")"
fi

qdrant_api_key="${GERCLAW_QDRANT_API_KEY:-}"
if [ -z "$qdrant_api_key" ]; then
    qdrant_api_key="$(read_or_create_secret "$runtime_root/secrets/qdrant.api-key")"
fi

if [ -z "${GERCLAW_DATABASE_URL:-}" ]; then
    export GERCLAW_DATABASE_URL="postgresql+asyncpg://gerclaw:${postgres_password}@localhost:5432/gerclaw"
fi
if [ -z "${GERCLAW_REDIS_URL:-}" ]; then
    export GERCLAW_REDIS_URL="redis://:${redis_password}@localhost:6379/0"
fi
if [ -z "${GERCLAW_QDRANT_URL:-}" ]; then
    export GERCLAW_QDRANT_URL="http://localhost:6333"
fi
export GERCLAW_QDRANT_API_KEY="$qdrant_api_key"
export GERCLAW_LOCAL_SECRET_DIR="${GERCLAW_LOCAL_SECRET_DIR:-$runtime_root/secrets}"
mkdir -p "$GERCLAW_LOCAL_SECRET_DIR"

if [ -z "${GERCLAW_CORS_ORIGINS:-}" ]; then
    export GERCLAW_CORS_ORIGINS='["https://moonnight-gerclaw.ms.show"]'
fi

postgres_bin_dir="$(pg_config --bindir)"
if [ ! -s "$postgres_dir/PG_VERSION" ]; then
    echo "[GerClaw] initializing PostgreSQL data directory"
    printf '%s\n' "$postgres_password" >"$runtime_root/secrets/postgres.init-password"
    "$postgres_bin_dir/initdb" \
        -D "$postgres_dir" \
        -U gerclaw \
        --pwfile="$runtime_root/secrets/postgres.init-password" \
        --auth-host=scram-sha-256 \
        --auth-local=scram-sha-256 \
        >/dev/null
    rm -f "$runtime_root/secrets/postgres.init-password"
fi

if ! "$postgres_bin_dir/pg_ctl" \
    -D "$postgres_dir" \
    -o "-h 127.0.0.1 -p 5432 -c unix_socket_directories=$postgres_dir" \
    -l "$postgres_dir/server.log" \
    start >/dev/null; then
    echo "[GerClaw] PostgreSQL failed to start" >&2
    cat "$postgres_dir/server.log" >&2 || true
    exit 1
fi
echo "[GerClaw] PostgreSQL process started"

if ! PGPASSWORD="$postgres_password" "$postgres_bin_dir/createdb" \
    -h 127.0.0.1 \
    -p 5432 \
    -U gerclaw \
    gerclaw \
    2>"$postgres_dir/createdb.log"; then
    if ! PGPASSWORD="$postgres_password" "$postgres_bin_dir/psql" \
        -h 127.0.0.1 \
        -p 5432 \
        -U gerclaw \
        -d postgres \
        -tAc "SELECT 1 FROM pg_database WHERE datname = 'gerclaw'" \
        | grep -q 1; then
        echo "[GerClaw] PostgreSQL database creation failed" >&2
        cat "$postgres_dir/createdb.log" >&2 || true
        exit 1
    fi
fi
echo "[GerClaw] PostgreSQL database ready"

redis-server \
    --bind 127.0.0.1 \
    --port 6379 \
    --requirepass "$redis_password" \
    --dir "$redis_dir" \
    --appendonly yes \
    --daemonize no \
    >"$redis_dir/server.log" 2>&1 &
redis_pid=$!

QDRANT__SERVICE__API_KEY="$qdrant_api_key" \
QDRANT__SERVICE__HTTP_PORT=6333 \
QDRANT__SERVICE__GRPC_PORT=6334 \
QDRANT__STORAGE__STORAGE_PATH="$qdrant_dir" \
QDRANT__STORAGE__SNAPSHOTS_PATH="$qdrant_dir/snapshots" \
qdrant \
    >"$qdrant_dir/server.log" 2>&1 &
qdrant_pid=$!

wait_for_port() {
    host="$1"
    port="$2"
    attempts=0
    while ! python -c 'import socket, sys; s=socket.create_connection((sys.argv[1], int(sys.argv[2])), 1); s.close()' "$host" "$port" 2>/dev/null; do
        if [ "$host:$port" = "localhost:6333" ] && ! kill -0 "$qdrant_pid" 2>/dev/null; then
            echo "[GerClaw] Qdrant exited before becoming ready" >&2
            cat "$qdrant_dir/server.log" >&2 || true
            exit 1
        fi
        attempts=$((attempts + 1))
        if [ "$attempts" -ge 60 ]; then
            echo "service did not become ready: $host:$port" >&2
            if [ "$host:$port" = "localhost:6333" ]; then
                cat "$qdrant_dir/server.log" >&2 || true
            fi
            exit 1
        fi
        sleep 1
    done
}

wait_for_port localhost 5432
echo "[GerClaw] PostgreSQL ready"
wait_for_port localhost 6379
echo "[GerClaw] Redis ready"
wait_for_port localhost 6333
echo "[GerClaw] Qdrant ready"

cd /app/api
echo "[GerClaw] applying database migrations"
alembic upgrade head
echo "[GerClaw] starting API and Web"
uvicorn gerclaw_api.main:app --host 0.0.0.0 --port 8000 &
api_pid=$!

cleanup() {
    kill "$api_pid" 2>/dev/null || true
    kill "$redis_pid" 2>/dev/null || true
    kill "$qdrant_pid" 2>/dev/null || true
    "$postgres_bin_dir/pg_ctl" -D "$postgres_dir" stop -m fast >/dev/null 2>&1 || true
}
trap cleanup INT TERM EXIT

cd /app/web
exec node server.js
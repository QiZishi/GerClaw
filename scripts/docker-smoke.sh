#!/usr/bin/env bash
# Run a destructive-to-itself, empty-volume production-compose smoke test.
#
# This command intentionally requires explicit permission because building the
# local RAG index invokes configured embedding/rerank providers. It never joins
# the regular ``gerclaw`` Compose project and always removes its own volumes.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SMOKE_KNOWLEDGE_BASE="${ROOT_DIR}/scripts/fixtures/docker-smoke-knowledge"

if [[ "${GERCLAW_RUN_DOCKER_SMOKE:-}" != "1" ]]; then
  echo "set GERCLAW_RUN_DOCKER_SMOKE=1 to run the destructive empty-volume Docker smoke" >&2
  exit 2
fi
if [[ "${GERCLAW_RUN_EXTERNAL:-}" != "1" ]]; then
  echo "set GERCLAW_RUN_EXTERNAL=1 because empty-volume RAG indexing calls configured providers" >&2
  exit 2
fi

API_PORT="${GERCLAW_DOCKER_SMOKE_API_PORT:-18080}"
WEB_PORT="${GERCLAW_DOCKER_SMOKE_WEB_PORT:-13000}"
if ! [[ "${API_PORT}" =~ ^[0-9]{2,5}$ ]] || (( API_PORT < 1024 || API_PORT > 65535 )); then
  echo "GERCLAW_DOCKER_SMOKE_API_PORT must be an unoccupied TCP port from 1024 to 65535" >&2
  exit 2
fi
if ! [[ "${WEB_PORT}" =~ ^[0-9]{2,5}$ ]] || (( WEB_PORT < 1024 || WEB_PORT > 65535 )); then
  echo "GERCLAW_DOCKER_SMOKE_WEB_PORT must be an unoccupied TCP port from 1024 to 65535" >&2
  exit 2
fi
if curl --silent --show-error --fail --connect-timeout 2 --max-time 3 "http://127.0.0.1:${API_PORT}/health/live" >/dev/null 2>&1; then
  echo "Docker smoke port ${API_PORT} is already serving HTTP; choose another port" >&2
  exit 2
fi
if curl --silent --show-error --fail --connect-timeout 2 --max-time 3 "http://127.0.0.1:${WEB_PORT}/" >/dev/null 2>&1; then
  echo "Docker smoke web port ${WEB_PORT} is already serving HTTP; choose another port" >&2
  exit 2
fi
if [[ ! -d "${SMOKE_KNOWLEDGE_BASE}" ]]; then
  echo "Docker smoke knowledge-base fixture is missing" >&2
  exit 1
fi

PROJECT="gerclaw-smoke-${UID:-local}-${RANDOM}"
COMPOSE=(
  docker compose
  --project-name "${PROJECT}"
  --file "${ROOT_DIR}/docker-compose.yml"
)

cleanup() {
  "${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

wait_for_http() {
  local path="$1"
  local expected_status="$2"
  local expected_body="$3"
  local port="${4:-${API_PORT}}"
  local deadline=$((SECONDS + 240))
  local response

  while (( SECONDS < deadline )); do
    response="$(curl --silent --show-error --connect-timeout 2 --max-time 5 --write-out $'\n%{http_code}' \
      "http://127.0.0.1:${port}${path}" 2>/dev/null || true)"
    if [[ "${response}" == *$'\n'"${expected_status}" ]] \
      && grep --quiet --fixed-strings "${expected_body}" <<<"${response}"; then
      return 0
    fi
    sleep 2
  done

  echo "timed out waiting for ${path} to return ${expected_status}" >&2
  return 1
}

cd "${ROOT_DIR}"
export API_PORT
export WEB_PORT
# A real empty-volume index is required to prove the runtime path.  A small,
# versioned corpus keeps this deployment smoke bounded; full-corpus indexing is
# an operational job and must not make the release gate take tens of minutes.
export GERCLAW_KNOWLEDGE_BASE_HOST_PATH="${SMOKE_KNOWLEDGE_BASE}"

echo "==> Starting isolated empty-volume Compose project ${PROJECT}"
"${COMPOSE[@]}" up --detach --build postgres redis qdrant migrate api web
wait_for_http "/health/live" "200" '"status":"alive"'
wait_for_http "/" "200" "GerClaw" "${WEB_PORT}"

echo "==> Building the empty-volume local RAG index"
"${COMPOSE[@]}" --profile ops run --rm rag-index
wait_for_http "/health/ready" "200" '"status":"ready"'

api_uid="$("${COMPOSE[@]}" exec --no-TTY api id -u)"
if [[ "${api_uid}" == "0" ]]; then
  echo "API container must not run as root" >&2
  exit 1
fi
web_uid="$("${COMPOSE[@]}" exec --no-TTY web id -u)"
if [[ "${web_uid}" == "0" ]]; then
  echo "Web container must not run as root" >&2
  exit 1
fi

echo "==> Restarting API against its existing smoke volumes"
"${COMPOSE[@]}" restart api
wait_for_http "/health/live" "200" '"status":"alive"'
wait_for_http "/health/ready" "200" '"status":"ready"'

echo "PASS: full-stack web/API empty-volume migration/index/readiness/restart/non-root Docker smoke"

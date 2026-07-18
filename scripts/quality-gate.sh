#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="${ROOT_DIR}/apps/api"
MVP_DIR="${ROOT_DIR}/apps/mvp"
MODE="${1:-quick}"

step() {
  echo
  echo "==> $1"
}

backend_gate() {
  step "Backend format, lint, types, migration graph, tests and coverage"
  cd "${API_DIR}"
  .venv/bin/ruff format --check src tests
  .venv/bin/ruff check src tests
  .venv/bin/mypy src/gerclaw_api
  heads="$(.venv/bin/alembic heads)"
  echo "${heads}"
  if [[ "$(grep -c '(head)' <<<"${heads}")" -ne 1 ]]; then
    echo "Alembic must expose exactly one migration head" >&2
    return 1
  fi
  .venv/bin/pytest -q
}

frontend_gate() {
  step "Frontend lint and production build"
  cd "${MVP_DIR}"
  npm run lint
  npm run build
}

security_gate() {
  step "Dependency and source security scans"
  (
    cd "${API_DIR}"
    audit_requirements="$(mktemp)"
    trap 'rm -f "${audit_requirements}"' EXIT
    uvx --from bandit bandit -r src -q
    uv export --locked --all-extras --no-emit-project --no-header \
      --no-annotate --output-file "${audit_requirements}" >/dev/null
    uvx pip-audit --strict --requirement "${audit_requirements}"
  )
  step "Locked frontend dependency audit"
  (
    cd "${MVP_DIR}"
    npm audit --omit=dev --audit-level=high
  )
  step "Production Python runtime SBOM"
  cd "${ROOT_DIR}"
  docker compose build api
  sbom_output="$(mktemp)"
  trap 'rm -f "${sbom_output}"' EXIT
  python3 "${ROOT_DIR}/scripts/generate_runtime_sbom.py" \
    --image "${GERCLAW_API_IMAGE:-gerclaw-api}" \
    --lock "${API_DIR}/uv.lock" \
    --output "${sbom_output}"
}

require_integration_env() {
  : "${GERCLAW_TEST_DATABASE_URL:?set GERCLAW_TEST_DATABASE_URL to a dedicated *_test database}"
  : "${GERCLAW_TEST_REDIS_URL:?set GERCLAW_TEST_REDIS_URL}"
  : "${GERCLAW_TEST_QDRANT_URL:?set GERCLAW_TEST_QDRANT_URL}"
  : "${GERCLAW_TEST_QDRANT_API_KEY:?set GERCLAW_TEST_QDRANT_API_KEY}"
  : "${GERCLAW_TEST_KNOWLEDGE_BASE_PATH:?set GERCLAW_TEST_KNOWLEDGE_BASE_PATH}"
  database_without_query="${GERCLAW_TEST_DATABASE_URL%%\?*}"
  if [[ "${database_without_query##*/}" != *_test ]]; then
    echo "GERCLAW_TEST_DATABASE_URL must name a dedicated database ending in _test" >&2
    exit 2
  fi
}

migration_gate() {
  : "${GERCLAW_TEST_DATABASE_URL:?set GERCLAW_TEST_DATABASE_URL to a dedicated *_test database}"
  database_without_query="${GERCLAW_TEST_DATABASE_URL%%\?*}"
  if [[ "${database_without_query##*/}" != *_test ]]; then
    echo "GERCLAW_TEST_DATABASE_URL must name a dedicated database ending in _test" >&2
    exit 2
  fi
  step "Alembic upgrade and model-to-migration check"
  cd "${API_DIR}"
  GERCLAW_DATABASE_URL="${GERCLAW_TEST_DATABASE_URL}" .venv/bin/alembic upgrade head
  GERCLAW_DATABASE_URL="${GERCLAW_TEST_DATABASE_URL}" .venv/bin/alembic check
}

integration_gate() {
  require_integration_env
  migration_gate
  step "Real PostgreSQL, Redis and Qdrant integration"
  cd "${API_DIR}"
  GERCLAW_RUN_INTEGRATION=1 .venv/bin/pytest -q -m "not external"
}

external_gate() {
  if [[ "${GERCLAW_RUN_EXTERNAL:-}" != "1" ]]; then
    echo "set GERCLAW_RUN_EXTERNAL=1 to permit paid provider calls" >&2
    exit 2
  fi
  require_integration_env
  step "Real external provider tests"
  cd "${API_DIR}"
  GERCLAW_RUN_INTEGRATION=1 .venv/bin/pytest \
    tests/test_real_external_services.py -m external -s --no-cov
}

harness_self_test() {
  step "Development Harness negative self-tests"
  "${ROOT_DIR}/scripts/test-quality-gate.sh"
}

docker_gate() {
  step "Docker configuration and image build"
  cd "${ROOT_DIR}"
  docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet
  docker compose -f docker-compose.yml -f docker-compose.dev.yml build api web
}

docker_smoke_gate() {
  step "Empty-volume Docker smoke"
  "${ROOT_DIR}/scripts/docker-smoke.sh"
}

e2e_gate() {
  : "${GERCLAW_E2E_BASE_URL:?set GERCLAW_E2E_BASE_URL to a running local frontend}"
  case "${GERCLAW_E2E_BASE_URL}" in
    http://127.0.0.1:*|http://localhost:*)
      ;;
    *)
      echo "GERCLAW_E2E_BASE_URL must be an explicit local HTTP URL" >&2
      exit 2
      ;;
  esac
  step "Playwright browser smoke"
  cd "${ROOT_DIR}"
  npx --yes --package @playwright/cli playwright-cli close >/dev/null 2>&1 || true
  open_output="$(npx --yes --package @playwright/cli playwright-cli open "${GERCLAW_E2E_BASE_URL}" 2>&1)"
  echo "${open_output}"
  if grep -q "### Error" <<<"${open_output}"; then
    npx --yes --package @playwright/cli playwright-cli close >/dev/null 2>&1 || true
    echo "Playwright could not open the local frontend" >&2
    return 1
  fi
  npx --yes --package @playwright/cli playwright-cli snapshot
  origin_output="$(npx --yes --package @playwright/cli playwright-cli eval "location.origin")"
  echo "${origin_output}"
  if ! grep -Fq "\"${GERCLAW_E2E_BASE_URL%/}\"" <<<"${origin_output}"; then
    npx --yes --package @playwright/cli playwright-cli close >/dev/null 2>&1 || true
    echo "Playwright opened an unexpected origin" >&2
    return 1
  fi
  npx --yes --package @playwright/cli playwright-cli close
}

case "${MODE}" in
  backend)
    backend_gate
    ;;
  frontend)
    frontend_gate
    ;;
  quick)
    backend_gate
    frontend_gate
    harness_self_test
    ;;
  security)
    security_gate
    ;;
  integration)
    integration_gate
    ;;
  migration)
    migration_gate
    ;;
  external)
    external_gate
    ;;
  docker)
    docker_gate
    ;;
  docker-smoke)
    docker_smoke_gate
    ;;
  e2e)
    e2e_gate
    ;;
  full)
    backend_gate
    frontend_gate
    harness_self_test
    security_gate
    ;;
  *)
    echo "usage: scripts/quality-gate.sh {backend|frontend|quick|security|migration|integration|external|e2e|docker|docker-smoke|full}" >&2
    exit 2
    ;;
esac

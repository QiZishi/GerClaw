#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="${ROOT_DIR}/apps/api"
GATE="${ROOT_DIR}/scripts/quality-gate.sh"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TEMP_DIR}"' EXIT

expect_failure() {
  local label="$1"
  shift
  if "$@" >"${TEMP_DIR}/${label}.log" 2>&1; then
    echo "negative self-test unexpectedly passed: ${label}" >&2
    return 1
  fi
  echo "PASS: ${label} failed closed"
}

expect_failure unknown-mode "${GATE}" deliberately-unknown
expect_failure missing-migration-url env -u GERCLAW_TEST_DATABASE_URL "${GATE}" migration
expect_failure unsafe-production-url env \
  GERCLAW_TEST_DATABASE_URL='postgresql+asyncpg://user:secret@127.0.0.1:5432/gerclaw' \
  "${GATE}" migration
expect_failure unsafe-integration-url env \
  GERCLAW_TEST_DATABASE_URL='postgresql+asyncpg://user:secret@127.0.0.1:5432/gerclaw' \
  GERCLAW_TEST_REDIS_URL='redis://127.0.0.1:6379/15' \
  GERCLAW_TEST_QDRANT_URL='http://127.0.0.1:6333' \
  GERCLAW_TEST_QDRANT_API_KEY='self-test-only' \
  GERCLAW_TEST_KNOWLEDGE_BASE_PATH="${ROOT_DIR}" \
  "${GATE}" integration

# The backend gate has just produced real coverage data. A deliberately stricter
# threshold proves that coverage.py preserves its non-zero failure status.
expect_failure coverage-threshold \
  "${API_DIR}/.venv/bin/coverage" report --data-file="${API_DIR}/.coverage" --fail-under=99

# A fake npm executable lets lint succeed and fails only the production build,
# proving that the second command's non-zero status is not swallowed.
mkdir -p "${TEMP_DIR}/bin"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "npm %s\n" "$*"' \
  'if [[ "$*" == "run lint" ]]; then exit 0; fi' \
  'if [[ "$*" == "run build" ]]; then exit 23; fi' \
  'exit 24' >"${TEMP_DIR}/bin/npm"
chmod +x "${TEMP_DIR}/bin/npm"
expect_failure frontend-build env PATH="${TEMP_DIR}/bin:${PATH}" "${GATE}" frontend
grep -Fq 'npm run build' "${TEMP_DIR}/frontend-build.log"
echo "PASS: frontend lint reached build and build exit was preserved"

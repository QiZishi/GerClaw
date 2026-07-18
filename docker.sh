#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose --project-directory "${ROOT_DIR}" --file "${ROOT_DIR}/docker-compose.yml")
COMMAND="${1:-up}"

read_env_value() {
  local key="$1"
  [[ -f "${ROOT_DIR}/.env" ]] || return 0
  awk -F= -v target="${key}" '$1 == target { value = substr($0, index($0, "=") + 1); gsub(/^[[:space:]"]+|[[:space:]"]+$/, "", value); print value; exit }' "${ROOT_DIR}/.env"
}

WEB_PORT_VALUE="${WEB_PORT:-$(read_env_value WEB_PORT)}"
API_PORT_VALUE="${API_PORT:-$(read_env_value API_PORT)}"
WEB_PORT_VALUE="${WEB_PORT_VALUE:-3000}"
API_PORT_VALUE="${API_PORT_VALUE:-8000}"

usage() {
  printf '%s\n' \
    "GerClaw Docker 管理脚本" \
    "" \
    "用法：./docker.sh <命令>" \
    "" \
    "  init      首次部署：构建、启动、建立知识库索引并检查服务" \
    "  up        构建并启动完整系统（默认）" \
    "  down      停止系统，保留数据库和索引卷" \
    "  restart   重启 Web 与 API" \
    "  index     重建或增量更新外部医学知识库索引" \
    "  test      在隔离测试数据库中运行后端集成测试" \
    "  status    查看容器与健康状态" \
    "  logs      持续查看 Web 与 API 日志" \
    "  help      显示本帮助"
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    printf '%s\n' "未找到 Docker。请先安装并启动 Docker Desktop。" >&2
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    printf '%s\n' "当前 Docker 未提供 Compose v2。请升级 Docker Desktop。" >&2
    exit 1
  fi
}

ensure_configuration() {
  if [[ -f "${ROOT_DIR}/.env" ]]; then
    return
  fi
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  printf '%s\n' \
    "已创建 ${ROOT_DIR}/.env。" \
    "请先填写模型、语音、Embedding、Rerank、搜索和 MinerU 配置，再重新执行本命令。" >&2
  exit 2
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local deadline=$((SECONDS + 240))
  while (( SECONDS < deadline )); do
    if curl --silent --show-error --fail --connect-timeout 2 --max-time 5 "${url}" >/dev/null 2>&1; then
      return
    fi
    sleep 2
  done
  printf '%s\n' "等待 ${label} 超时：${url}" >&2
  return 1
}

start_stack() {
  "${COMPOSE[@]}" config --quiet
  "${COMPOSE[@]}" up --detach --build
  wait_for_http "http://127.0.0.1:${API_PORT_VALUE}/health/live" "API"
  wait_for_http "http://127.0.0.1:${WEB_PORT_VALUE}/" "Web"
}

show_access() {
  printf '%s\n' \
    "GerClaw 已启动。" \
    "Web： http://127.0.0.1:${WEB_PORT_VALUE}" \
    "API： http://127.0.0.1:${API_PORT_VALUE}" \
    "状态：./docker.sh status" \
    "日志：./docker.sh logs"
}

require_docker

case "${COMMAND}" in
  init)
    ensure_configuration
    start_stack
    "${COMPOSE[@]}" --profile ops run --rm rag-index
    wait_for_http "http://127.0.0.1:${API_PORT_VALUE}/health/ready" "完整服务 readiness"
    show_access
    ;;
  up)
    ensure_configuration
    start_stack
    show_access
    ;;
  down)
    "${COMPOSE[@]}" down --remove-orphans
    ;;
  restart)
    ensure_configuration
    "${COMPOSE[@]}" restart api web
    wait_for_http "http://127.0.0.1:${API_PORT_VALUE}/health/live" "API"
    wait_for_http "http://127.0.0.1:${WEB_PORT_VALUE}/" "Web"
    show_access
    ;;
  index)
    ensure_configuration
    "${COMPOSE[@]}" up --detach postgres redis qdrant migrate api
    "${COMPOSE[@]}" --profile ops run --rm rag-index
    wait_for_http "http://127.0.0.1:${API_PORT_VALUE}/health/ready" "完整服务 readiness"
    ;;
  test)
    ensure_configuration
    "${COMPOSE[@]}" --profile test run --rm test-api
    ;;
  status)
    "${COMPOSE[@]}" ps
    printf '\nAPI live：'
    curl --silent --show-error --fail --connect-timeout 2 --max-time 5 "http://127.0.0.1:${API_PORT_VALUE}/health/live" || true
    printf '\nAPI ready：'
    curl --silent --show-error --fail --connect-timeout 2 --max-time 5 "http://127.0.0.1:${API_PORT_VALUE}/health/ready" || true
    printf '\nWeb：'
    if curl --silent --show-error --fail --connect-timeout 2 --max-time 5 "http://127.0.0.1:${WEB_PORT_VALUE}/" >/dev/null; then
      printf '%s\n' "可访问"
    else
      printf '%s\n' "不可访问"
    fi
    ;;
  logs)
    "${COMPOSE[@]}" logs --follow --tail 200 web api
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

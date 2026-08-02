#!/usr/bin/env bash

set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "用法：$0 <需要 MODELSCOPE_API_KEY 的命令> [参数…]" >&2
  exit 64
fi

if [[ -n "${MODELSCOPE_API_KEY:-}" ]]; then
  exec "$@"
fi

credential_host="${MODELSCOPE_KEYCHAIN_HOST:-www.modelscope.cn}"
credential_helper="$(git --exec-path)/git-credential-osxkeychain"

if [[ ! -x "$credential_helper" ]]; then
  echo "未找到 git-credential-osxkeychain：$credential_helper" >&2
  echo "请先安装或启用 macOS Keychain credential helper。" >&2
  exit 78
fi

credentials="$(printf 'protocol=https\nhost=%s\n\n' "$credential_host" | "$credential_helper" get)"
api_key="$(printf '%s\n' "$credentials" | awk -F= '$1 == "password" { print substr($0, index($0, "=") + 1); exit }')"

if [[ -z "$api_key" ]]; then
  echo "Keychain 中没有找到 $credential_host 的 ModelScope 凭据。" >&2
  echo "请在 Keychain 中保存一次 ModelScope Token，之后无需重复输入。" >&2
  exit 78
fi

export MODELSCOPE_ENDPOINT="${MODELSCOPE_ENDPOINT:-https://modelscope.cn}"
export MODELSCOPE_API_KEY="$api_key"
exec "$@"

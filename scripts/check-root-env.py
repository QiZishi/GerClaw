#!/usr/bin/env python3
"""Verify the root-only GerClaw environment contract without printing secrets."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_NAMES = {".env", ".env.example", ".env.local"}


def parse_environment(path: Path) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    duplicates: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in values:
            duplicates.append(key)
        values[key] = value.strip()
    return values, duplicates


def is_secret(key: str) -> bool:
    return any(
        marker in key
        for marker in ("API_KEY", "SECRET", "PASSWORD", "TOKEN", "ENCRYPTION_KEY")
    )


def main() -> int:
    actual_path = ROOT / ".env"
    example_path = ROOT / ".env.example"
    if not actual_path.is_file() or not example_path.is_file():
        print("根目录必须同时存在 .env 与 .env.example。", file=sys.stderr)
        return 1

    nested = sorted(
        path.relative_to(ROOT)
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.name in ENV_NAMES
        and path.parent != ROOT
        and ".git" not in path.parts
        and "node_modules" not in path.parts
    )
    if nested:
        print("发现不允许的子目录环境文件：", file=sys.stderr)
        for path in nested:
            print(f"- {path}", file=sys.stderr)
        return 1

    actual, actual_duplicates = parse_environment(actual_path)
    example, example_duplicates = parse_environment(example_path)
    if actual_duplicates or example_duplicates:
        print("环境文件存在重复变量名。", file=sys.stderr)
        return 1
    if actual.keys() != example.keys():
        print(".env 与 .env.example 的变量集合不一致。", file=sys.stderr)
        return 1

    mismatches = [
        key
        for key in actual
        if not is_secret(key) and actual[key] != example[key]
    ]
    if mismatches:
        print("以下非密钥变量值不一致：" + "、".join(mismatches), file=sys.stderr)
        return 1

    lines = example_path.read_text(encoding="utf-8").splitlines()
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        comment = lines[index - 1].strip() if index else ""
        if not comment.startswith("#") or not any("\u4e00" <= char <= "\u9fff" for char in comment):
            print(f"{line.split('=', 1)[0]} 缺少紧邻的中文配置说明。", file=sys.stderr)
            return 1

    print(f"根环境配置契约通过：{len(actual)} 个变量，未发现子目录环境文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

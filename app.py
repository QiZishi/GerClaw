#!/usr/bin/env python3
"""GerClaw 的本地开发启动入口。

默认只启动 MVP 前端，避免在前端设计阶段无意拉起数据库或 API。
需要同时调试本地 FastAPI 时，显式传入 ``--api``；该模式会先启动开发
依赖、执行迁移，再并行运行 API 与前端。这个脚本不会读取、打印或修改
``.env`` 中的任何密钥。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "apps" / "mvp"
API_DIR = ROOT / "apps" / "api"


def require_command(command: str, install_hint: str) -> None:
    """Fail early with an actionable message when a required executable is absent."""
    if shutil.which(command) is None:
        raise RuntimeError(f"未找到 {command}。{install_hint}")


def run_checked(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def start_frontend(port: int) -> subprocess.Popen[bytes]:
    if not (FRONTEND_DIR / "node_modules").is_dir():
        raise RuntimeError(
            "前端依赖尚未安装。请先执行：cd apps/mvp && npm install"
        )
    return subprocess.Popen(
        ["npm", "run", "dev", "--", "-p", str(port)],
        cwd=FRONTEND_DIR,
    )


def start_api_dependencies() -> None:
    require_command("docker", "请安装 Docker Desktop 后重试。")
    run_checked(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.dev.yml",
            "up",
            "-d",
            "postgres",
            "redis",
            "qdrant",
        ],
        cwd=ROOT,
    )


def start_local_api() -> subprocess.Popen[bytes]:
    require_command("uv", "请先安装 uv：https://docs.astral.sh/uv/")
    run_checked(["uv", "sync", "--all-extras", "--dev"], cwd=API_DIR)
    run_checked(["uv", "run", "alembic", "upgrade", "head"], cwd=API_DIR)
    return subprocess.Popen(["uv", "run", "gerclaw-api"], cwd=API_DIR)


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="启动 GerClaw 本地开发环境（默认仅启动 MVP 前端）。"
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="同时启动本地 API、PostgreSQL、Redis 和 Qdrant，并先执行迁移。",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3000,
        help="前端端口（默认：3000）。",
    )
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("--port 必须在 1 到 65535 之间。")

    try:
        require_command("npm", "请安装 Node.js 20+ 与 npm 后重试。")
        api_process: subprocess.Popen[bytes] | None = None
        if args.api:
            start_api_dependencies()
            api_process = start_local_api()

        frontend_process = start_frontend(args.port)
        print(f"\nGerClaw 前端已启动： http://127.0.0.1:{args.port}")
        if api_process is not None:
            print("GerClaw API 已启动：  http://127.0.0.1:8000")
        print("按 Ctrl+C 可停止本次启动的前端/API 进程。\n")

        try:
            frontend_exit = frontend_process.wait()
            if frontend_exit:
                return frontend_exit
            return 0
        except KeyboardInterrupt:
            return 0
        finally:
            terminate(frontend_process)
            if api_process is not None:
                terminate(api_process)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"启动失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

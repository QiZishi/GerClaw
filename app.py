#!/usr/bin/env python3
"""GerClaw 的本地开发启动入口。

默认启动本地 FastAPI、MVP 前端及其开发依赖；该模式会先启动开发
依赖、执行迁移，再并行运行 API 与前端。仅审阅前端时可显式传入
``--frontend-only``；本机已经安装 PostgreSQL、Redis 和 Qdrant 时可传入
``--no-docker``。为让宿主机进程使用本地端口，脚本只读取根目录配置并在
子进程内转换 Docker 服务名；不会打印
或修改 ``.env`` 中的任何值。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "apps" / "mvp"
API_DIR = ROOT / "apps" / "api"
LOCAL_SERVICE_HOSTS = {
    "postgres": "127.0.0.1",
    "redis": "127.0.0.1",
    "qdrant": "127.0.0.1",
    "api": "127.0.0.1",
}


def read_root_environment() -> dict[str, str]:
    """Read root configuration for child-process adaptation without logging it."""

    env_file = ROOT / ".env"
    if not env_file.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def replace_service_host(url: str) -> str:
    """Turn a compose-network URL into its published localhost equivalent."""

    parsed = urlsplit(url)
    replacement = LOCAL_SERVICE_HOSTS.get(parsed.hostname or "")
    if replacement is None:
        return url

    user_info, separator, host_port = parsed.netloc.rpartition("@")
    host_port = host_port if separator else parsed.netloc
    original_host = parsed.hostname or ""
    if host_port == original_host:
        replacement_host_port = replacement
    elif host_port.startswith(f"{original_host}:"):
        replacement_host_port = f"{replacement}{host_port[len(original_host):]}"
    else:
        return url
    netloc = f"{user_info}@{replacement_host_port}" if separator else replacement_host_port
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def local_process_environment() -> dict[str, str]:
    """Build root-env-only host settings without changing the configuration file."""

    environment = os.environ.copy()
    root_environment = read_root_environment()
    environment.update(root_environment)
    for key in (
        "GERCLAW_DATABASE_URL",
        "GERCLAW_REDIS_URL",
        "GERCLAW_QDRANT_URL",
        "GERCLAW_API_URL",
    ):
        value = root_environment.get(key) or environment.get(key)
        if value:
            environment[key] = replace_service_host(value)

    knowledge_base = root_environment.get("GERCLAW_KNOWLEDGE_BASE_PATH")
    knowledge_base_host = root_environment.get("GERCLAW_KNOWLEDGE_BASE_HOST_PATH")
    if knowledge_base == "/knowledge-base" and knowledge_base_host:
        local_knowledge_base = Path(knowledge_base_host).expanduser()
        if not local_knowledge_base.is_absolute():
            local_knowledge_base = (ROOT / local_knowledge_base).resolve()
        if local_knowledge_base.is_dir():
            environment["GERCLAW_KNOWLEDGE_BASE_PATH"] = str(local_knowledge_base)
    if root_environment.get("GERCLAW_LOCAL_SECRET_DIR") == "/app/workspaces/secrets":
        environment["GERCLAW_LOCAL_SECRET_DIR"] = str(
            Path.home() / ".local" / "share" / "gerclaw" / "secrets"
        )
    return environment


def require_command(command: str, install_hint: str) -> None:
    """Fail early with an actionable message when a required executable is absent."""
    if shutil.which(command) is None:
        raise RuntimeError(f"未找到 {command}。{install_hint}")


def run_checked(
    command: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def start_frontend(port: int, *, env: dict[str, str]) -> subprocess.Popen[bytes]:
    if not (FRONTEND_DIR / "node_modules").is_dir():
        raise RuntimeError(
            "前端依赖尚未安装。请先执行：cd apps/mvp && npm install"
        )
    return subprocess.Popen(
        ["npm", "run", "dev", "--", "-p", str(port)],
        cwd=FRONTEND_DIR,
        env=env,
    )


def ensure_process_started(
    process: subprocess.Popen[bytes], *, label: str, grace_period_seconds: float = 2.0
) -> None:
    """Do not announce a service until its launcher survived initial startup."""

    deadline = time.monotonic() + grace_period_seconds
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(f"{label} 启动后立即退出（退出码 {exit_code}）。")
        time.sleep(0.1)


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
    environment = local_process_environment()
    venv_bin = API_DIR / ".venv" / "bin"
    alembic = venv_bin / "alembic"
    api = venv_bin / "gerclaw-api"
    if alembic.is_file() and api.is_file():
        run_checked([str(alembic), "upgrade", "head"], cwd=API_DIR, env=environment)
        return subprocess.Popen([str(api)], cwd=API_DIR, env=environment)

    raise RuntimeError(
        "未检测到 apps/api/.venv。请在项目根目录执行："
        "python3.12 -m venv apps/api/.venv && "
        "source apps/api/.venv/bin/activate && "
        "python -m pip install -r requirements.txt"
    )


def run_rag_index() -> None:
    """Index the external knowledge directory through the same local env adaptation."""

    environment = local_process_environment()
    local_indexer = API_DIR / ".venv" / "bin" / "gerclaw-rag-index"
    if local_indexer.is_file():
        run_checked([str(local_indexer)], cwd=API_DIR, env=environment)
        return
    raise RuntimeError(
        "未检测到 apps/api/.venv/bin/gerclaw-rag-index。请在项目根目录执行："
        "python3.12 -m venv apps/api/.venv && "
        "source apps/api/.venv/bin/activate && "
        "python -m pip install -r requirements.txt"
    )


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
        description="启动 GerClaw 本地开发环境（默认启动 API、依赖与 MVP 前端）。"
    )
    launch_mode = parser.add_mutually_exclusive_group()
    launch_mode.add_argument(
        "--api",
        action="store_true",
        help="兼容旧命令：显式启动本地 API、PostgreSQL、Redis 和 Qdrant，并先执行迁移。",
    )
    launch_mode.add_argument(
        "--frontend-only",
        action="store_true",
        help="仅启动 MVP 前端；不启动 API、开发依赖或执行迁移。",
    )
    launch_mode.add_argument(
        "--index-only",
        action="store_true",
        help="仅建立或增量更新医学知识库索引，完成后退出。",
    )
    parser.add_argument(
        "--no-docker",
        action="store_true",
        help="不启动 Docker 依赖；使用本机已运行的 PostgreSQL、Redis 和 Qdrant。",
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
    if args.frontend_only and args.no_docker:
        parser.error("--frontend-only 已不会启动依赖，无需同时传入 --no-docker。")

    api_process: subprocess.Popen[bytes] | None = None
    frontend_process: subprocess.Popen[bytes] | None = None
    try:
        if args.index_only:
            if not args.no_docker:
                start_api_dependencies()
            run_rag_index()
            print("GerClaw 医学知识库索引已更新。")
            return 0
        require_command("npm", "请安装 Node.js 20+ 与 npm 后重试。")
        if not args.frontend_only:
            if not args.no_docker:
                start_api_dependencies()
            api_process = start_local_api()

        frontend_process = start_frontend(args.port, env=local_process_environment())
        ensure_process_started(frontend_process, label="前端")
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
        if frontend_process is not None:
            terminate(frontend_process)
        if api_process is not None:
            terminate(api_process)
        print(f"启动失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

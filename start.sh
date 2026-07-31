#!/usr/bin/env bash
# GerClaw 本地开发启动脚本
# 使用方式：./start.sh [选项]

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印带颜色的消息
info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查命令是否存在
check_command() {
    if ! command -v "$1" &> /dev/null; then
        error "未找到 $1。$2"
        exit 1
    fi
}

# 检查 Docker 是否运行
check_docker() {
    if ! docker info &> /dev/null; then
        error "Docker 未运行。请先启动 Docker Desktop。"
        echo ""
        echo "在 macOS 上，你可以："
        echo "  1. 打开 Docker Desktop 应用"
        echo "  2. 或者运行：open -a Docker"
        echo ""
        exit 1
    fi
    info "Docker 已运行"
}

# 显示帮助信息
show_help() {
    cat << EOF
GerClaw 本地开发启动脚本

使用方式: ./start.sh [选项]

选项:
    -h, --help          显示此帮助信息
    -a, --api-only      仅启动 API 和依赖服务（不启动前端）
    -f, --frontend-only 仅启动前端（不启动 API 和依赖服务）
    -n, --no-docker     不启动 Docker 依赖（使用本地已运行的 PostgreSQL、Redis、Qdrant）
    -i, --index-only    仅建立或更新医学知识库索引
    -p, --port PORT     指定前端端口（默认：3000）

示例:
    ./start.sh                    # 启动完整环境（API + 前端 + 依赖服务）
    ./start.sh --frontend-only    # 仅启动前端
    ./start.sh --no-docker        # 使用本地服务启动
    ./start.sh --port 3001        # 使用自定义端口启动前端

首次使用前请确保:
    1. 已安装 Python 3.12+、Node.js 20+、Docker
    2. 已配置 .env 文件（可从 .env.example 复制）
    3. 已安装前端依赖：cd apps/mvp && npm install
    4. 已安装后端依赖：python3.12 -m venv apps/api/.venv && source apps/api/.venv/bin/activate && pip install -r requirements.txt
EOF
}

# 主函数
main() {
    local args=()

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -a|--api-only)
                args+=("--api")
                shift
                ;;
            -f|--frontend-only)
                args+=("--frontend-only")
                shift
                ;;
            -n|--no-docker)
                args+=("--no-docker")
                shift
                ;;
            -i|--index-only)
                args+=("--index-only")
                shift
                ;;
            -p|--port)
                if [[ -n "${2:-}" ]]; then
                    args+=("--port" "$2")
                    shift 2
                else
                    error "--port 需要指定端口号"
                    exit 1
                fi
                ;;
            *)
                error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # 检查基础依赖
    info "检查基础依赖..."
    check_command "python3" "请安装 Python 3.12+"
    check_command "node" "请安装 Node.js 20+"
    check_command "npm" "请安装 npm"

    # 检查 .env 文件
    if [[ ! -f ".env" ]]; then
        if [[ -f ".env.example" ]]; then
            warn ".env 文件不存在，正在从 .env.example 复制..."
            cp .env.example .env
            warn "请编辑 .env 文件配置必要的环境变量"
        else
            error ".env 文件不存在且没有 .env.example 模板"
            exit 1
        fi
    fi

    # 检查前端依赖
    if [[ ! -d "apps/mvp/node_modules" ]]; then
        warn "前端依赖未安装，正在安装..."
        cd apps/mvp && npm install && cd ../..
    fi

    # 检查后端虚拟环境
    if [[ ! -d "apps/api/.venv" ]]; then
        warn "后端虚拟环境未创建，正在创建..."
        python3.12 -m venv apps/api/.venv
        source apps/api/.venv/bin/activate
        pip install -r requirements.txt
        deactivate
    fi

    # 如果需要 Docker，检查 Docker 状态
    if [[ ! " ${args[*]} " =~ " --no-docker " ]] && [[ ! " ${args[*]} " =~ " --frontend-only " ]]; then
        check_docker
    fi

    # 启动应用
    info "启动 GerClaw..."
    python3 app.py "${args[@]}"
}

main "$@"

# GerClaw API

GerClaw 二阶段生产后端基础。当前里程碑提供真实 PostgreSQL、Redis、Qdrant，JWT scope/tenant 隔离，Redis 原子限流，Trace/反馈/bad-case 数据闭环，以及按设计要求第四章拆分的 Agent Harness、Memory、Agentic RAG、Skill、Input/Output、Tool Protocol 边界。

本阶段没有伪造医疗对话或 RAG 结果。真实 AgentScope Agentic RAG、对话、CGA、处方与 Voice 业务实现在后续独立变更集接入。

## 配置与安全

根目录 `.env` 是当前及后续开发的唯一 canonical 配置源；`apps/mvp/.env*` 不再由 Compose 加载。Settings 只在 development/test 兼容旧 `NEXT_PUBLIC_*` 名称，production 检测到浏览器前缀密钥会直接拒绝启动。

本地开发会在 `GERCLAW_LOCAL_SECRET_DIR` 生成权限为 `0600` 的随机 JWT 和 AES-256-GCM 数据密钥；Docker 使用持久化 `runtime_secrets` 卷。Production 必须由 Secret Manager 显式注入 `GERCLAW_AUTH_JWT_SECRET` 和 base64 编码的 32-byte `GERCLAW_DATA_ENCRYPTION_KEY`，弱密码、placeholder、空密钥和外部 HTTP endpoint 会 fail-fast。

Trace/feedback/metrics 均要求已验证 JWT scope，tenant/actor 只从 token claims 派生。Trace JSONB 只接受枚举事件和 allowlist 审计元数据；自由文本敏感列使用 AES-256-GCM envelope encryption，禁止存储原始 Chain-of-Thought。

## Docker 运行

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

- 基础 `docker-compose.yml` 仅将 API 绑定到 `127.0.0.1`，PostgreSQL/Redis/Qdrant 位于 internal data network，不发布 host ports。
- `docker-compose.dev.yml` 只为本机调试把数据端口绑定到 `127.0.0.1`，同时创建隔离的 `gerclaw_test` 数据库。
- Redis 强制密码，Qdrant server/client 使用同一个 API Key；匿名 Redis/Qdrant 请求会被拒绝。
- Alembic 由一次性 `migrate` service 执行并持有 PostgreSQL advisory lock；API 副本只直接启动 Uvicorn，不会并发执行 DDL。
- 本地知识库从仓库同级 `../本地知识库/md` 只读挂载到 `/knowledge-base`，不得复制进镜像或 Git。

## 验证

静态检查与不依赖容器的测试：

```bash
cd apps/api
uv sync --all-extras --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -m 'not integration and not external'
```

真实依赖集成测试只允许专用 `_test` 数据库；fixture 会拒绝业务库 URL，避免 `TRUNCATE` 误删业务数据：

```bash
export GERCLAW_TEST_DATABASE_URL='postgresql+asyncpg://gerclaw:local-postgres-only@127.0.0.1:5432/gerclaw_test'
export GERCLAW_TEST_REDIS_URL='redis://:local-redis-only@127.0.0.1:6379/15'
export GERCLAW_TEST_QDRANT_URL='http://127.0.0.1:6333'
export GERCLAW_TEST_QDRANT_API_KEY='local-qdrant-only'
export GERCLAW_TEST_KNOWLEDGE_BASE_PATH='/absolute/path/to/本地知识库/md'
GERCLAW_RUN_INTEGRATION=1 uv run pytest -m 'not external' -rs
```

真实外部服务 smoke test 不提供 mock，会产生真实调用与可能的费用。命令从 `apps/api` 执行并只加载根 `.env`：

```bash
set -a
source ../../.env
set +a
GERCLAW_RUN_EXTERNAL=1 uv run pytest tests/test_real_external_services.py -m external -s --no-cov
```

2026-07-14 的真实结果为 `4 passed`：三套 AgentScope LLM、MiMo TTS→ASR、SiliconFlow BGE-M3 Embedding/Rerank、Tavily 均通过；AnySearch 另按官方 skill 的 `get_sub_domains → health vertical search` 流程验证。

## API

- `GET /health/live`：公开进程存活探针。
- `GET /health/ready`：公开 PostgreSQL、Redis、Qdrant、AgentScope 与知识库就绪状态，不返回连接信息。
- `GET /metrics`：要求 `metrics:read` scope。
- `POST /api/v1/traces`：要求 `trace:write`；durable Trace ID 来自合法 `X-Trace-ID` 或服务端生成值。
- `GET /api/v1/traces/{trace_id}`：要求 `trace:read`；使用 `after_sequence`/`limit≤100` 分页。
- `POST /api/v1/traces/{trace_id}/events`：要求 `trace:write`；`event_id` 幂等，单 Trace 有事件总量上限。
- `POST /api/v1/traces/{trace_id}/finish`：要求 `trace:write`；完整 payload 指纹幂等。
- `POST /api/v1/feedback`：要求 `feedback:write`；负反馈自动创建 bad case。

所有受保护 API 共享每主体 `100 requests/minute` 的 Redis 原子限流；Redis 故障时写链路 fail closed。请求体在 JSON 解析前限制为 256 KiB，嵌套深度、节点数、字符串长度和非有限浮点数也在 Pydantic 信任边界拒绝。

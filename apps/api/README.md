# GerClaw API

GerClaw 二阶段生产后端。当前里程碑提供真实 PostgreSQL、Redis、Qdrant，JWT scope/tenant 隔离，Redis 原子限流，Trace/反馈/bad-case 数据闭环，以及按设计要求第四章拆分的 Agent Harness、Memory、Agentic RAG、Skill、Input/Output、Tool Protocol 边界。

本地医学 Agentic RAG 已使用 AgentScope 2.0.4 `RAGMiddleware(mode="agentic")` 真实接入；对话 Agent Harness、CGA、处方与 Voice 业务仍在后续独立变更集实现。本阶段不伪造医疗对话或检索结果。

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

## 本地医学 Agentic RAG

生产检索链路为：Markdown 安全解析与章节分块 → SiliconFlow `BAAI/bge-m3` dense embedding + 本地中英文 lexical sparse vector → Qdrant prefetch/RRF → SiliconFlow `BAAI/bge-reranker-v2-m3` 重排。AgentScope 通过 `search_knowledge` 工具调用同一条检索链路，不存在第二套简化实现。

首次索引是独立 one-shot job，不随 API 副本启动：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  --profile ops run --rm rag-index
```

索引 job 必须与已启动栈使用相同的 Compose 文件组合；上述命令对应本地 dev 启动方式。仅使用 base Compose 的部署环境则执行 `docker compose --profile ops run --rm rag-index`。API、migration 和索引 job 共用 `GERCLAW_API_IMAGE`，避免 one-shot job 产生不一致镜像。`rag-index` 还依赖 PostgreSQL readiness，并在整个同步期间持有独立连接上的 session-level advisory lock；第二个容器或进程会等待锁。锁连接注册 asyncpg termination listener：进程退出时 PostgreSQL 自动释放锁，连接意外丢失时 listener 会立即取消仍存活的索引 task，使其 fail-stop 且不执行按共享确定性 ID 的失败清理，下一 worker 再安全恢复 staging generation。

索引器以相对路径、原始内容哈希和 chunk 位置生成确定性 chunk ID；每次取得 PostgreSQL 锁后再生成包含 `txid_current()` 与随机 nonce 的 writer fencing generation，Qdrant point ID 由 chunk ID、index version 和 fencing generation 共同生成。因此被取消 writer 的远端 late upsert 只能形成不可检索的独立 staging point，不能覆盖新 writer。新 generation 完整写入后才激活；stale cleanup 先 scroll 快照旧 point IDs，再只按显式 ID 删除，禁止使用会匹配未来 generation 的宽 filter。索引开始时会回收遗留 staging。manifest 只用于安全幂等 skip，只承认某来源唯一且 chunk 序列完整的已激活 generation；语料撤回检测另行扫描包含多 generation/残缺 generation 的全量 source→document ID inventory，因此即使 cleanup outage 使 manifest 拒绝某 source，源文件删除仍会清掉其全部显式 point IDs。stale delete 若出现 lost acknowledgement，会重试同一批显式 IDs 且绝不回滚已激活新代，持续故障则保留完整新旧代供下次同步清理。因此重复执行可恢复中断更新，并跳过未变化文档、替换变化文档、删除已移除文档。大批量 embedding 由 `GERCLAW_RAG_EMBEDDING_TOKENS_PER_MINUTE` 控制共享 TPM 预算，429 会触发所有待处理批次的共享退避。

2026-07-15 的真实全量结果为 436/436 文档、39,837 chunks、失败 0；第二次同步为 `indexed=0, skipped=436, chunks_written=0`。跌倒、压疮、焦虑、肌少症、冠心病五类代表查询均在 top-3 命中对应本地目录文献。

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

2026-07-15 的完整真实回归结果为 `91 passed`、0 skipped、一次性全量覆盖率 87.58%；独立审阅按 unit+integration 与 external 分组复测的主覆盖率为 87.55%，4 个 external tests 全部通过。三套 AgentScope LLM、MiMo TTS→ASR、SiliconFlow BGE-M3 Embedding/Rerank、Tavily、PostgreSQL、Redis、Qdrant、AgentScope `search_knowledge`、RAG HTTP/Trace 重试、索引中断/lost-ack/锁断连/远端 late-commit fencing/撤回证据清理与失败 Bad Case 链路均通过。

## API

- `GET /health/live`：公开进程存活探针。
- `GET /health/ready`：公开 PostgreSQL、Redis、Qdrant、AgentScope、知识库及索引一致性状态，不返回连接信息。
- `GET /metrics`：要求 `metrics:read` scope。
- `POST /api/v1/traces`：要求 `trace:write`；durable Trace ID 来自合法 `X-Trace-ID` 或服务端生成值。
- `GET /api/v1/traces/{trace_id}`：要求 `trace:read`；使用 `after_sequence`/`limit≤100` 分页。
- `POST /api/v1/traces/{trace_id}/events`：要求 `trace:write`；`event_id` 幂等，单 Trace 有事件总量上限。
- `POST /api/v1/traces/{trace_id}/finish`：要求 `trace:write`；完整 payload 指纹幂等。
- `POST /api/v1/feedback`：要求 `feedback:write`；负反馈自动创建 bad case。
- `GET /api/v1/rag/status`：要求 `rag:read`；返回语料/索引文档数、chunk 数和检索模式。
- `POST /api/v1/rag/retrieve`：要求 `rag:read`；执行 dense+sparse RRF + rerank，返回相对文件/章节/chunk citation 和医疗免责声明，并自动完成 Trace start/event/finish。相同 Trace ID 只能重放 keyed fingerprint 一致的同一请求，completed Trace 重试不追加重复事件。

所有受保护 API 共享每主体 `100 requests/minute` 的 Redis 原子限流；Redis 故障时写链路 fail closed。请求体在 JSON 解析前限制为 256 KiB，嵌套深度、节点数、字符串长度和非有限浮点数也在 Pydantic 信任边界拒绝。

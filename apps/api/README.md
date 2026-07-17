# GerClaw API

GerClaw 二阶段生产后端。当前已提供真实 PostgreSQL、Redis、Qdrant，JWT scope/tenant 隔离，Redis 原子限流，Trace 与反馈/Bad Case 基础写入，以及按设计要求第四章拆分的 Agent Harness、Memory、Agentic RAG、Search、Skill、Input/Output、Tool Protocol 边界。患者/医生本地账号已支持注册、登录、refresh 轮换、登出和改密；医生资质、患者授权和跨患者权限仍未启用。反馈查询、Bad Case 治理和 Eval 回放闭环仍待后续里程碑完成。

本地医学 Agentic RAG 已使用 AgentScope 2.0.4 `RAGMiddleware(mode="agentic")` 真实接入；长期健康记忆已使用 `Mem0Middleware(mode="both")` + GerClaw adapter 接入，并以加密 PostgreSQL 为事实源、PHI-free Qdrant revision vector 为语义索引。联网医疗证据由 AgentScope 只读 `web_search` 工具调用生产 `SearchModule`，严格执行 AnySearch `/mcp` JSON-RPC 主通道、Tavily 备用通道和 S/A/B/C 来源分级。声明式 Skill 已通过 `LocalSkillLoader`、`Skill` 和 `Toolkit` viewer 接入同一生产 Harness，支持四个内置包、加密版本注册表、会话选择、Markdown/ZIP 安装和真实模型生成待审阅草稿。生产对话 Harness 已形成三模型依次兜底、安全 SSE、加密会话/画像、Redis session lease 和幂等 Trace 重放闭环。CGA、处方、上传文档与 Voice 的完整后端业务仍在后续独立变更集实现。本阶段不伪造医疗对话、检索、联网来源、记忆或 Skill 结果。

## 配置与安全

根目录 `.env` 是当前及后续开发的唯一 canonical 配置源；`apps/mvp/.env*` 不再由 Compose 加载。Settings 只在 development/test 兼容旧 `NEXT_PUBLIC_*` 名称，production 检测到浏览器前缀密钥会直接拒绝启动。

本地开发会在 `GERCLAW_LOCAL_SECRET_DIR` 生成权限为 `0600` 的随机 JWT、访客身份和 AES-256-GCM 数据密钥；Docker 使用持久化 `runtime_secrets` 卷。Production 必须由 Secret Manager 显式注入 `GERCLAW_AUTH_JWT_SECRET`、独立且稳定的 `GERCLAW_GUEST_IDENTITY_SECRET` 和 base64 编码的 32-byte `GERCLAW_DATA_ENCRYPTION_KEY`，弱密码、placeholder、空密钥和外部 HTTP endpoint 会 fail-fast。JWT 密钥可独立轮换；访客身份密钥轮换需要身份迁移方案。

Trace/feedback/metrics 均要求已验证 JWT scope，tenant/actor 只从 token claims 派生。Trace JSONB 只接受枚举事件和 allowlist 审计元数据；自由文本敏感列使用 AES-256-GCM envelope encryption，禁止存储原始 Chain-of-Thought。

## Docker 运行

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

- 基础 `docker-compose.yml` 仅将 API 绑定到 `127.0.0.1`，PostgreSQL/Redis/Qdrant 位于 internal data network，不发布 host ports。
- `docker-compose.dev.yml` 只为本机调试把数据端口绑定到 `127.0.0.1`，同时创建隔离的 `gerclaw_test` 数据库。
- `test` profile 的 `test-api` 使用单独的 `gerclaw-api-test` 镜像、`gerclaw_test` 数据库和 Redis DB 15，默认只运行 `not external`。它不会覆盖运行中的生产 API 镜像或业务数据库：`docker compose --profile test up --build --abort-on-container-exit --exit-code-from test-api test-api`。
- Redis 强制密码，Qdrant server/client 使用同一个 API Key；匿名 Redis/Qdrant 请求会被拒绝。
- Alembic 由一次性 `migrate` service 执行并持有 PostgreSQL advisory lock；API 副本只直接启动 Uvicorn，不会并发执行 DDL。
- 本地知识库从仓库同级 `../本地知识库/md` 只读挂载到 `/knowledge-base`，不得复制进镜像或 Git。

已启动 Compose 栈上的确定性用药审查并发复验从 API 容器执行，避免将访客身份密钥导出到宿主机。它只使用合成输入并输出 PHI-free 聚合结果；硬上限为 10，并不衡量外部模型、RAG、MinerU 或临床正确性：

```bash
docker compose exec -T api python /app/scripts/perf_medication_review_workflow.py \
  --base-url http://127.0.0.1:8000 --concurrency 10
```

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

回归检索仅接受已审阅的合成用例，默认不会调用 embedding 或 rerank 服务。需要在同一不可变索引上进行一次显式的真实检索复验时，使用以下受限命令；输出只包含 case ID、匹配数和索引版本，不回显查询、文献正文或检索结果：

```bash
uv run python -m gerclaw_api.modules.evals.rag_cli \
  --allow-external-rag \
  --cases evals/rag-retrieval-reviewed-v1.json \
  --index-version markdown-heading-v1:lexical-cjk-ngram-v1:BAAI/bge-m3:1024 \
  --top-k 5 --max-cases 6
```

该评测只验证特定合成问题对特定公共语料的召回契约；它不证明医学正确性、模型质量、完整临床 workflow 或系统吞吐能力。

## 联网医疗证据 Search

`ProductionSearchModule` 是后端唯一联网证据入口。它在 query 出站前脱敏手机号、证件号、邮箱和显式姓名；AnySearch 瞬态失败最多重试一次，随后才切换 Tavily，认证或 schema 错误直接降级。双 Provider 都失败时返回 `SEARCH_UNAVAILABLE`，不允许模型记忆冒充最新信息。

结果只接受 HTTPS 来源，按 WHO/FDA/NIH/政府（S）、权威学会与期刊（A）、专业平台（B）、通用来源（C）分级，论坛、广告和推广来源作为 D 级过滤。AgentScope 收到的正文用 `<untrusted-web-evidence>` 隔离，`tool_result` SSE 同时提供卡片所需结构化结果；最终 citation 的 `corpus` 为 `web`。本地 RAG 仍是医学事实第一证据来源，`workflow=cga` 时 Toolkit 不注册 `web_search`。

`extract_content` 只允许标准 443 公网 HTTPS URL；调用 Provider 前校验全部 DNS 地址，以受限 GET 连接已验证公网 IP，同时用原 hostname 做 TLS SNI/证书校验，并逐跳重新校验最多 5 次 redirect，阻断 HEAD/GET 差异跳转、loopback、私网、link-local、metadata 和 DNS rebinding。搜索 Trace 只保存 Provider、结果数、重试序号、耗时和权威级别，不保存 query、snippet 或网页正文。相同 Trace ID 的重试必须匹配 actor、执行类型和 keyed request fingerprint；completed Trace 可重新执行查询但不追加重复事件，冲突请求返回 409。

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

2026-07-15 的 0017 回归结果：默认套件 `239 passed, 21 skipped`、覆盖率 81.20%；真实 PostgreSQL/Redis/Qdrant 套件 `254 passed, 6 deselected`、覆盖率 88.37%；全新库 Alembic `upgrade → downgrade → upgrade` 到 `e41b8c2a2017 (head)` 通过。根 `.env` 的 6 项真实外部测试均取得通过结果，覆盖三套 AgentScope LLM、Mimo ASR/TTS、SiliconFlow embedding/rerank、Tavily 和完整 Chat；一次全套执行为 `5 passed, 1 failed`，失败用例已成功召回 `memories=2`，但供应商在可见输出后断流并被系统正确 fail closed，随后该真实用例隔离重跑 `1 passed`。跨会话测试由真实模型从首轮 user message 抽取青霉素过敏/阿司匹林用药，第二 session 的 AgentScope 自动召回并实际调用 `search_memory`；同时验证重放不重复、PG ciphertext、加密 revision audit、同名多次重大事件不覆盖、Qdrant 无 PHI payload、本地 RAG citation、测试 collection 清理、readiness 强制复验重建、多副本初始化竞争安全，以及事实确认接口在 vector upsert 后数据库失败时精确补偿本 Unit of Work 的 fenced point。模型候选的配置超时现在覆盖完整 stream，持续心跳无法无限占用执行槽；超时前无公开输出才 failover，已有公开输出则 fail closed。未使用 mock 成功路径。

2026-07-15 的 0019 最终回归结果：默认套件 `349 passed, 31 skipped`、coverage 80.02%；真实 PostgreSQL/Redis/Qdrant 非 external 套件 `370 passed, 10 deselected`、coverage 87.05%；根 `.env` 的真实模型生成草稿→注册→AgentScope Skill viewer→本地 Agentic RAG→实际 skill/version Trace 由开发者和独立审阅者分别复现通过。浏览器真实链路验证了会话级 Skill 隔离与刷新恢复、停止流终态、红旗症状确定性短路和患者模式适老化。最终应用 Docker 运行验收仍在全部临床功能与前后端联调完成后统一执行，当前只能声明 API image 可构建。

## API

- `GET /health/live`：公开进程存活探针。
- `GET /health/ready`：公开 PostgreSQL、Redis、Qdrant、AgentScope、知识库、RAG 索引、Memory collection 及 Search 双通道配置状态，不返回连接信息或健康文本。
- `GET /metrics`：要求 `metrics:read` scope。
- `POST /api/v1/traces`：要求 `trace:write`；durable Trace ID 来自合法 `X-Trace-ID` 或服务端生成值。
- `GET /api/v1/traces/{trace_id}`：要求 `trace:read`；使用 `after_sequence`/`limit≤100` 分页。
- `POST /api/v1/traces/{trace_id}/events`：要求 `trace:write`；`event_id` 幂等，单 Trace 有事件总量上限。
- `POST /api/v1/traces/{trace_id}/finish`：要求 `trace:write`；完整 payload 指纹幂等。
- `POST /api/v1/feedback`：要求 `feedback:write`；负反馈自动创建 bad case。
- `GET /api/v1/rag/status`：要求 `rag:read`；返回语料/索引文档数、chunk 数和检索模式。
- `POST /api/v1/rag/retrieve`：要求 `rag:read`；执行 dense+sparse RRF + rerank，返回相对文件/章节/chunk citation 和医疗免责声明，并自动完成 Trace start/event/finish。相同 Trace ID 只能重放 keyed fingerprint 一致的同一请求，completed Trace 重试不追加重复事件。
- `POST /api/v1/sessions`：要求 `chat:write`；创建或幂等返回当前 tenant/actor 所属会话。
- `GET /api/v1/sessions/{session_id}/messages`：要求 `chat:read`；只返回当前 tenant/actor 的有界解密历史，其他主体统一返回 404。
- `POST /api/v1/chat`：要求 `chat:write`；运行 AgentScope ReAct + 本地 Agentic RAG，返回 `agent_start/thinking/tool_call/tool_result/text_delta/done` SSE。医疗请求无本地证据时 fail closed；`done` 仅在加密消息和 completed Trace 已提交后发送。
- `POST /api/v1/search/query`：要求 `search:read`；执行脱敏后的 AnySearch→Tavily 联网证据查询并生成 PHI-free Trace。
- `POST /api/v1/search/extract`：要求 `search:read`；只提取经 DNS/redirect SSRF 校验的公网 HTTPS 正文。
- `POST /api/v1/auth/register`、`/login`、`/refresh`、`/logout`、`/password`：本地账号会话；用户名加密、密码使用 scrypt、refresh token 仅存 HMAC 指纹。当前 refresh token 只可交由受信任同源 BFF，浏览器 cookie/CSRF 接入仍待完成。
- `GET /api/v1/search/status`：要求 `search:read`；仅返回主备通道是否配置，不执行计费搜索。
- `GET /api/v1/memory/profile`：要求 `memory:read`；返回当前 actor 的加密健康画像投影和 evidenced facts，未建档访客返回空画像。
- `POST /api/v1/memory/facts/{fact_id}/decision`：要求 `memory:write`；用 expected revision 确认或拒绝当前 actor 的事实，跨主体统一 404。

所有受保护 API 共享每主体 `100 requests/minute` 的 Redis 原子限流；Redis 故障时写链路 fail closed。请求体在 JSON 解析前限制为 256 KiB，嵌套深度、节点数、字符串长度和非有限浮点数也在 Pydantic 信任边界拒绝。

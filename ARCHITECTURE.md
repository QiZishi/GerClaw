# GerClaw 架构

本文描述已运行并经验证的架构边界。产品需求以 [设计要求](docs/references/gerclaw设计要求.md) 为最高权威；每项是否真正完成以 [需求矩阵](docs/REQUIREMENTS_MATRIX.md) 与可复现执行证据为准。目录、UI 或 README 本身不是功能完成证据。

## 1. 系统目标

GerClaw 将适老化患者服务、医生辅助工作台与可追溯的 Agent Runtime 组合为同一条受治理链路。它提供证据绑定的辅助信息和待临床复核草案，而不替代医生判断、急救服务或正式处方系统。

### 运行拓扑

```text
患者 / 医生 / 管理员浏览器
        │ 浏览器安全请求体、HttpOnly 会话 cookie
        ▼
apps/mvp ─ Next.js 16 页面 + server-only BFF ─ Zod
        │ 短期 JWT；不暴露 Provider/DB key
        ▼
apps/api ─ FastAPI + Pydantic + AgentScope 2.0.4
  ├─ API routes：认证、HTTP/SSE、错误映射、依赖注入
  ├─ services：聊天、会话、临床收集、账户、Trace、限流
  ├─ modules：可替换的领域能力与严格契约
  ├─ repositories：SQLAlchemy 加密事实源
  ├─ PostgreSQL：账户、会话、消息、事实、草案、授权、Trace
  ├─ Redis：限流、session lease、取消
  ├─ Qdrant：公共医学语料与无 PHI Memory reference vector
  └─ server-only providers：LLM、Embedding/Rerank、Search、ASR/TTS、MinerU
```

`apps/mvp` 是唯一运行前端。`apps/web` 仍是预留目录，禁止复制一套平行 BFF 或业务客户端。根 `app.py` 是本地启动入口；Docker Compose 运行 migration、API、PostgreSQL、Redis、Qdrant 和可选 RAG index。

## 2. 分层规则

```text
React component
  → apps/mvp/src/services                 # 唯一浏览器业务 client
  → apps/mvp/app/api                      # server-only BFF + Zod
  → apps/api/api/routes                   # HTTP/SSE + principal + DI
  → apps/api/services                     # 业务编排
  → apps/api/modules + repositories       # 能力契约 / 数据存取
  → PostgreSQL / Redis / Qdrant / provider adapters
```

- 组件不得内嵌 Provider URL、密钥、临床规则或绕过 services 调用 BFF。
- 路由不得拥有业务状态机；它们只做认证、请求/响应映射和依赖注入。
- `modules/` 负责单一能力、Protocol/Pydantic 契约和独立测试；`services/` 负责跨模块工作流；`repositories/` 负责持久化。
- 模型、工具、搜索、文件、图片和数据库回读均为不可信边界。未知字段、尺寸超限、版本不符或所有权不符必须受控失败，不能静默修补。

## 3. 推荐技术栈

| 层级 | 当前技术 | 使用边界 |
|---|---|---|
| Web | Next.js 16、React 19、TypeScript、Tailwind、Zod | `apps/mvp` 是唯一功能前端与 BFF；外部 Provider 只由 server-only 路由调用 |
| API / Agent | FastAPI、Pydantic、AgentScope 2.0.4 | 认证、Runtime Harness、业务模块、SSE 与 Provider adapter |
| 持久化 | PostgreSQL、Redis、Qdrant | PostgreSQL 是加密事实源；Redis 处理 lease/限流/取消；Qdrant 不存 PHI 正文 |
| 部署 | Docker Compose、Alembic、uv/npm | 已通过空卷迁移/RAG/health/重启/non-root smoke；不是高可用拓扑证明 |

所有模型、外部 URL、密钥和协议均通过环境变量配置；实现遵循“设计要求优先、AgentScope 能力优先、必要时才引入补充依赖”。

## 4. 身份、数据与授权

### 3.1 主体

- 登录入口默认显示；用户可选择无账号进入一次性患者服务。访客在当前浏览器会话内可用，但历史不会在下次进入复现。
- 服务端 JWT 生成 tenant/actor/role/scope；前端不能自报医生、患者、管理员或权限。
- PostgreSQL 是加密事实源。Redis lease 与 PostgreSQL fencing token 共同保证同一会话 turn 只有一个写入者。

### 3.2 患者授权

`consent` 的事实模型为：**患者 → 指定医生 → 单一 resource scope → 到期时间 → revision**。有效授权仅允许以下受限投影：

| scope | 医生可见 | 明确排除 |
|---|---|---|
| `health_profile_read` | 已确认健康事实 | pending/inactive 事实、聊天、附件、Trace |
| `cga_report_read` | 已完成 CGA 摘要 | 原始答案、活动评估 |
| `prescription_draft_review` | 草案与自己的复核意见 | 可执行处方、其他医生意见、附件/Trace |
| `medication_review_read` | input revision、finding、规则来源 | 用药原文、会话、附件、Trace |
| `risk_alert_read` | 当前 alert ledger | 聊天、量表答案、用药详情、附件、Trace |

consumer 在每次读取前都查询有效 grant；撤回、过期、跨 tenant、角色不符和未知患者均 fail closed 且不允许枚举。

## 5. 分层依赖

依赖必须从上向下单向流动：React component → 前端 services → server-only BFF/Zod → FastAPI routes → services → modules/repositories → 数据源或 provider adapter。模块不得反向依赖 UI、HTTP route 或具体浏览器状态；跨模块业务流程只能在 `services/` 中编排。

### 对话与 Agent Runtime

```text
POST /api/v1/chat
  → principal / rate limit / input_output normalization
  → Trace replay 或 Redis lease + PostgreSQL fencing
  → workflow registry + security profile admission
  → request-scoped AgentState / governed Toolkit
  → red-flag short circuit 或 RAG / Memory / Skill / Search / model router
  → evidence and public-output validation
  → atomic message + audit + terminal Trace commit
  → SSE done
```

- `AgentState` 只属于当前 turn。历史由加密 PostgreSQL 会话恢复，不能由模型临时状态代替。
- `orchestration.ChatTurnCoordinator` 统一处理 replay、lease、取消/失败终态和指标，不读取临床正文，也不发起第二次模型调用。
- `runtime` 是唯一工具治理边界：capability、schema、大小、timeout、budget、permission、permit 和审计均由服务端决定。
- SSE 只发送公开状态摘要、工具状态、文本、引用与 done；不发送隐藏推理、provider body、密钥或原始图片。`done` 仅在原子提交后发送。
- 主/备用模型只在尚未产生可见文本或工具调用时切换。模型最大输出配置为 32,768；处方 workflow 的整流程预算为 600 秒。

### 医疗输出策略

本地知识库、受治理联网结果、用户文档和图片都可以成为 evidence。没有可追溯 evidence 的临床结论或调药候选不能进入临床产物；有 evidence 时可以输出带条件和依据的建议。患者端只在整段末尾显示一次复核提示；医生端直接显示建议、条件与证据。红旗症状仍优先输出立即就医信息。

## 6. 数据边界

浏览器请求、上传文件、图像、MinerU/ASR/TTS/LLM Provider 响应、检索片段、网页内容、工具输入输出及数据库回读都是不可信输入。它们均须先经过身份、schema/version、大小和所有权校验，再进入下游；PHI 只按 tenant/actor/session 最小化处理，不能写入前端 bundle、公共向量正文或非必要日志。

### 知识、记忆、文档和图片

### RAG

`rag` 以 Markdown→heading chunk→dense+sparse→RRF→rerank 实现本地优先检索。每个结果必须满足 `local-rag-evidence-v1`，包含真实相对路径、章节、chunk、来源类型和分数。索引写入使用 PostgreSQL advisory lock、generation fencing、staging→activate、撤回清理；API 副本不会在启动时索引。

### Memory

`memory` 保存加密、版本化健康事实；抽取结果可确认、拒绝、否定或失效。Qdrant 只保存无 PHI 的 reference vector。医生投影排除 `pending`/`inactive`；每次用户决定使用 `expected_revision`，避免最后写入覆盖。

### Document 与 Image

MinerU 只由同源 Next.js BFF 发送到 provider，FastAPI 将解析 Markdown 加密登记为当前 session 的输入。五大处方输入不可静默截断；普通聊天的截断由服务端明确决定。上传图片作为模型的多模态输入和 evidence，trace 记录 base64 输入；资料的文字/影像内容可分析，但不能改变权限或执行外部指令。上传资料不是公共 RAG 语料。

## 7. Agent-Legible Invariants

1. 浏览器只连 BFF；外部 Provider 只能由服务端 service/provider adapter 调用。
2. 不可信输入先验证、限长、隔离；未知字段和风险不明的外发失败时受控终止。
3. 未通过 schema 与 Runtime policy 的模型输出不得调用工具、写入数据库/Memory 或展示为医疗结论。
4. 临床高风险操作没有 evidence、授权或所需人工批准时，不得升级为可执行系统动作。
5. Trace、日志、评测和向量库不保存不必要的 PHI、凭据、用户原文或隐藏推理。
6. 目录、静态 UI、mock 或文档不构成完成证据；每项能力须有消费链路、测试和运行证据。

### 临床与交互模块

| 模块 | 运行能力 | 关键限制 |
|---|---|---|
| `cga` | PHQ-9、SAS、PSQI、Mini-Cog、MMSE；版本化题目、计分、报告、导出、音频 | 不验证动作、书写或图画；不替代专业评估 |
| `prescription` | 聊天式补充、10 份资料、273k 上限、evidence-bound 草案、Markdown/PDF/DOCX | `needs_clinician_review` 不是处方，不能发布或执行 |
| `medication_review` | reconciliation、`medication-rules-v4`、来源绑定 artifact、严重命中 alert | 有限规则未命中不代表安全，不是完整 Beers/DDI 审方 |
| `risk_alert` | Chat/CGA/严重用药信号的加密 ledger 与 acknowledgement | acknowledgement 不解除风险；没有通知/dispatch |
| `chronic_care` | 自述病情、测量账本、最近两值算术趋势 | 无阈值、目标、诊断或治疗解释 |
| `companion` | 受隔离的当前会话陪伴 | 无 Memory/RAG/Search/Skill/文档；红旗短路保留 |
| `voice` | FastAPI ASR、24kHz PCM16 TTS、浏览器本地播放控制 | 未验证真实人声质量或 provider 端暂停 |
| `skill` | 注册、导入、加载、生成、递增 SemVer 修订草稿 | 不自动保存、发布、启用或执行 |

## 8. 模块维护契约

`apps/api/src/gerclaw_api/modules/` 有 25 个实际模块。每个目录都必须同时含 `AGENTS.md` 和 `README.md`。README 的“维护与演进”章节是交接契约，必须说明：

1. 哪些改善可安全实施，及其所需的 schema/迁移/消费者同步；
2. 哪些所有权、版本、数据最小化、授权、终态或 provider 边界不可破坏；
3. 精确的单元/集成/并发和 p95 验收标准。

修改模块时先读模块 `AGENTS.md`，再读 README；不要以增加文件、mock 或静态 UI 代替真实 API/Runtime 消费链路。

## 9. 可观测性、Bad Case 与评测

- Trace 记录最小的 PHI-free 状态、workflow/version、受控工具和 terminal outcome；不保存 Chain-of-Thought。
- 负反馈产生 tenant-scoped、加密 Bad Case。管理员工作台只接收 SQL 聚合，不读取 case snapshot、图片、正文、Trace 或身份。
- `evals` 仅运行人工审核的合成 case；真实用户数据不能直接回放。RAG retrieval、Memory extraction、Skill draft、隐私 policy、规则与 Runtime profile 都有确定性基线。

## 10. 部署与性能

```text
Docker Compose
  postgres (encrypted fact source)
  redis    (lease / rate-limit / cancellation)
  qdrant   (vectors)
  migrate  (one-shot Alembic)
  api      (non-root FastAPI)
  rag-index (optional one-shot job)
```

已验证的性能边界仅限两条真实 Compose、最多 10 并发确定性 workload：安全短路 SSE 为 10/10 done、p50/p95 322/323ms；来源可追溯用药审查为 10/10、p50/p95 52/55ms。二者均验证 cross-actor 拒绝和唯一 completed Trace，均不包含外部模型、RAG、MinerU、完整五大处方或千级容量。

空卷 Docker smoke 已验证 migration、3 份受控文档 RAG index、health、重启和 non-root。生产高可用仍应拆分数据服务、provider egress、secret 管理、监控、备份和容量演练。

## 11. 验证顺序

```bash
scripts/quality-gate.sh quick
docker compose --profile test run --rm test-api
cd apps/mvp && npm test
GERCLAW_E2E_BASE_URL=http://127.0.0.1:3000 scripts/quality-gate.sh e2e
GERCLAW_RUN_DOCKER_SMOKE=1 GERCLAW_RUN_EXTERNAL=1 scripts/quality-gate.sh docker-smoke
```

外部 Provider 测试与空卷索引会产生真实请求，必须显式同意。任何运行失败必须保留稳定错误、停止向下游扩大影响，并如实写入 evidence/exec-plan；不得以“应当可用”替代运行结果。

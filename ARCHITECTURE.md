# GerClaw 系统架构

本文描述 GerClaw AI 辅助诊疗平台的系统上下文、运行组件、数据流、部署拓扑和扩展约束。产品功能与交互以 [GerClaw 设计要求](docs/references/gerclaw设计要求.md) 为最高依据。

## 1. 系统目标

GerClaw 的架构目标是把适老化交互、医生专业工作流和可追溯 AI Runtime 组合成一套可私有部署、可配置、可审计的 Web 应用。

核心设计目标：

1. 支持文本、语音、图片和文档的多模态输入。
2. 让医学建议、处方草案和用药审查结果关联可回溯证据。
3. 隔离患者、医生、管理员和访客数据，避免跨账户读取。
4. 将 LLM、搜索、语音、MinerU、Embedding 与 Rerank 封装为可替换 Provider。
5. 为长时间模型任务提供稳定状态、取消、失败恢复和终态一致性。
6. 通过外部知识库挂载、独立数据卷和容器化运行支持私有部署。

## 2. 架构总览

```text
患者 / 医生 / 管理员浏览器
        │ HTTPS、HttpOnly 会话 Cookie、版本化 JSON/SSE
        ▼
┌──────────────────────────────────────────────────────┐
│ Next.js Web + server-only BFF                        │
│ 页面、适老化交互、Zod 校验、Cookie、流式响应转发       │
└───────────────────────┬──────────────────────────────┘
                        │ 内部 HTTP
                        ▼
┌──────────────────────────────────────────────────────┐
│ FastAPI + AgentScope Runtime                         │
│ 认证授权、业务编排、Agent Harness、领域模块、Provider   │
└───────┬────────────────┬─────────────────┬───────────┘
        │                │                 │
        ▼                ▼                 ▼
 PostgreSQL           Redis             Qdrant
 加密事实源            lease/限流/取消     RAG/Memory 向量
        │
        └────────────── Server-side Provider adapters ──────┐
                                                            ▼
                   LLM / Search / ASR / TTS / MinerU /
                   Embedding / Rerank
```

浏览器只访问 Next.js BFF，不直接获取 Provider、数据库或向量库凭据。`apps/mvp` 是唯一 Web 前端；`apps/api` 是统一 API 与 Agent Runtime。

## 3. 技术栈

| 层级 | 技术 | 职责 |
|---|---|---|
| Web | Next.js 16、React 19、TypeScript、Tailwind CSS | 页面、角色工作台、适老化交互、音频控制、实时文档渲染 |
| BFF | Next.js Route Handlers、Zod | Cookie 会话、请求校验、受限 API 转发、SSE 代理 |
| API | FastAPI、Pydantic、SQLAlchemy、Alembic | 认证、业务服务、领域 API、持久化、迁移 |
| Agent | AgentScope 2.0.4 | Agent 生命周期、模型调用、工具编排和结构化输出 |
| 数据 | PostgreSQL 16、Redis 7、Qdrant | 事实数据、并发协调、向量检索 |
| AI 服务 | OpenAI-compatible/DashScope、SiliconFlow、AnySearch、Tavily、MiMo、MinerU | LLM、RAG、搜索、语音和文档解析 |
| 部署 | Docker、Docker Compose、非 root 容器 | 构建、启动、迁移、索引、健康检查和数据卷 |

Provider URL、API Key、模型名、协议、超时和能力声明均由环境变量或账户级加密配置提供。

## 4. 核心数据流

### 4.1 对话与多模态输入

```text
文本 / 音频 / 图片 / 已解析文档
  → BFF 输入校验与身份绑定
  → FastAPI 会话服务
  → Trace + session lease + fencing token
  → RAG / Memory / Skill / Search / model router
  → evidence 与公开输出校验
  → 消息、引用、Trace 原子提交
  → SSE 状态、文本、引用、done
```

音频先由 ASR 转写；图片作为原生 multimodal content block 发送给声明支持 image input 的模型；文档由 MinerU 转为 Markdown 后，以用户资料身份进入当前会话。图片和文档都会获得 evidence ID。图片 base64 被写入受控 Trace 输入，用于授权范围内的 Bad Case 分析。

### 4.2 五大处方

五大处方使用聊天式 intake：

1. 接收用户文字、语音、图片和最多 10 份文档。
2. MinerU 提取文档正文，输入上下文总上限为 273k 字符。
3. 服务端依据五大处方输入模板计算缺失字段。
4. Agent 最多用 5 轮对话补齐必要信息。
5. 模型生成结构化草案，并关联本地 RAG、联网结果和用户资料 evidence。
6. 前端在单页单栏中实时编辑、实时渲染，并支持导出。

产物状态为 `needs_clinician_review`。草案可以包含有依据的诊断方向、剂量调整和治疗候选，但不能自动签署或执行。

### 4.3 CGA 与语音

CGA 的问卷版本、题目、选项、计分和报告由服务端状态机管理。预录音频按量表版本绑定，Web 端使用全局音频协调器保证任一时刻只有一个题目或回答播放，并支持暂停、继续、停止与进度展示。

Mini-Cog 和 MMSE 涉及动作、绘图、书写、阅读等内容时，报告明确保留人工专业审核边界。

### 4.4 RAG

```text
外部 Markdown 知识库（只读挂载）
  → 文件发现与内容哈希
  → 结构化切分
  → Embedding
  → Qdrant staging generation
  → PostgreSQL manifest activation
  → Hybrid retrieval + RRF + Rerank
  → local-rag-evidence-v1 引用
```

索引器采用 generation fencing 和 staging-to-active 切换，避免并发索引或中断更新污染当前集合。患者上传资料不进入公共 RAG collection。

### 4.5 Memory 与 Skill

Memory 从会话中提取高置信度健康事实，正文加密保存在 PostgreSQL；Qdrant 只保存不含 PHI 正文的 reference vector。检索前按 tenant、actor 和状态过滤。

Skill 支持内置 Skill、Markdown/ZIP 导入、自然语言生成和递增 SemVer 修订。模型产物先进入待审阅状态，不会自动发布、启用或调用工具。

## 5. 分层依赖

依赖方向保持单向：

```text
React Component
  → apps/mvp/src/services
  → apps/mvp/app/api（server-only BFF）
  → apps/api/api/routes
  → apps/api/services
  → apps/api/modules + repositories
  → PostgreSQL / Redis / Qdrant / Provider adapters
```

- React 组件不直接拼接 Provider URL、临床规则或数据库请求。
- 前端业务调用集中在 `apps/mvp/src/services`，BFF 使用 Zod 校验浏览器边界。
- API route 负责认证、请求映射、依赖注入和错误语义，不承载跨模块状态机。
- `services` 负责业务编排、事务边界、重试、取消和多模块协调。
- `modules` 提供可替换领域能力、Protocol 与 Pydantic 合同。
- `repositories` 负责数据访问、所有权过滤和加密字段读写。
- 外部 AI 调用统一经过 server-side adapter，不从浏览器直连。

## 6. 数据边界

### 6.1 身份与角色

- 登录页是统一入口，同时允许访客进入患者端。
- 患者账户只能访问患者端，医生账户只能访问医生端，管理员可切换两端视角。
- 访客使用临时身份；数据进入后台分析链路，但前端会话结束后不恢复访客历史。
- 医生和患者之间没有聊天、通知或消息通信链路。
- 服务端根据签发的 principal 决定 tenant、actor、role 和 scope，前端不能自报角色。

### 6.2 数据存储

| 数据 | 存储 | 约束 |
|---|---|---|
| 账户、会话、消息、临床产物 | PostgreSQL | tenant/actor 隔离，敏感正文加密 |
| Trace、反馈、Bad Case | PostgreSQL | 最小化、加密、访问受限，不保存模型隐藏推理 |
| 限流、session lease、取消 | Redis | 有 TTL，不作为长期事实源 |
| 公共医学知识向量 | Qdrant | 来自外部只读 Markdown 语料 |
| Memory reference vector | Qdrant | 不包含 PHI 正文，通过 PostgreSQL reference 回读 |
| 图片 | 模型上下文 + 加密 Trace 输入 | evidence ID 绑定，base64 不写普通应用日志 |
| 用户文档 | PostgreSQL 加密资料 | 不进入公共 RAG，不跨账户共享 |

### 6.3 证据边界

本地知识库、受治理联网搜索和用户上传资料都属于证据来源。临床建议、诊断方向、调药候选和用药审查结论必须关联可追溯 evidence；缺乏证据的高风险内容不能进入临床产物。有证据时保留完整建议和条件，患者端只在全文末尾显示一次风险提示，医生端不做机械屏蔽。

### 6.4 并发与一致性

会话 turn 使用 Redis owner lease 与 PostgreSQL fencing token。assistant 消息、审计事件和 Trace 终态在同一事务提交；已完成请求可以按 trace replay，避免重复模型调用和重复写入。

## 7. Agent-Legible Invariants

1. 浏览器只访问 BFF；Provider 凭据、数据库连接和内部 API 不进入客户端 bundle。
2. 上传、模型、工具、检索、搜索和数据库回读均是不可信边界，必须先经过 schema、大小、版本、所有权和权限校验。
3. 图片可以被模型解读并作为证据，但图片内容不能更改系统权限、工具许可或执行控制。
4. 本地 RAG、联网搜索和用户资料都是合法 evidence source；缺少证据时才阻止高风险临床结论进入产物。
5. 患者与医生数据按 tenant/actor 隔离；不存在患者和医生之间的消息通信通道。
6. PostgreSQL 是事实源；Redis 和 Qdrant 的数据必须能通过稳定 ID 回到事实记录。
7. AgentState 只属于当前 turn；长期状态通过会话、Memory 和版本化临床产物恢复。
8. SSE 的 `done` 只能在消息与终态提交成功后发出；失败、取消和超时必须形成明确终态。
9. 模型 fallback 接收同一任务上下文、证据和输出 schema；产生可见输出后不得切换到另一模型拼接回答。
10. 五大处方、Skill、Memory 和工具参数必须通过版本化结构合同；未知版本或未知字段不能静默兼容。
11. Trace 不保存 Chain-of-Thought、凭据或无必要的 Provider 原始响应；图片 base64 进入专用加密字段而不是普通日志。
12. 患者上传文档和图片不能写入公共医学知识库。

## 8. 部署架构

```text
Reverse Proxy / TLS
        │
        ▼
Web container ── edge network ── API container
                                  │
                                  └── internal data network
                                      ├── PostgreSQL volume
                                      ├── Redis volume
                                      └── Qdrant volume

Read-only host knowledge base ── mount ── API / RAG index job
```

Compose 的服务职责：

| 服务 | 生命周期 | 职责 |
|---|---|---|
| `web` | 常驻 | Next.js 页面与 BFF |
| `api` | 常驻 | FastAPI 与 Agent Runtime |
| `migrate` | 一次性 | 启动前执行 Alembic migration |
| `postgres` | 常驻 | 事实数据和事务 |
| `redis` | 常驻 | lease、限流、取消和短期协调 |
| `qdrant` | 常驻 | RAG 与 Memory reference vectors |
| `rag-index` | 按需 | 增量索引外挂 Markdown 语料 |
| `test-api` | 按需 | 隔离测试数据库中的集成测试 |

`web` 只连接 edge network；数据库、Redis 和 Qdrant 位于 internal data network，默认不映射宿主机公网端口。Web 与 API 镜像使用多阶段构建和非 root 用户运行。知识库使用只读 bind mount，业务数据使用命名卷。

生产环境建议：

- 在 Web 前部署 TLS 反向代理或云负载均衡器。
- 使用 Secret Manager 注入 JWT、加密密钥和 Provider Key。
- 将 PostgreSQL、Redis、Qdrant 替换为带备份和监控的托管或高可用服务。
- 为 API 配置多副本、共享 Redis/Qdrant/PostgreSQL，并保持 migration 为单次任务。
- 对外部 Provider 配置出口白名单、超时、预算、熔断和告警。
- 定期备份 PostgreSQL 与 Qdrant，并进行恢复演练。

## 9. 可观测性与质量

系统使用结构化日志、健康检查、Prometheus 指标、Trace、用户反馈和去标识化 Bad Case 观察运行质量。

- `/health/live` 表示 API 进程可服务。
- `/health/ready` 检查 PostgreSQL、Redis、Qdrant、知识库、RAG index、Memory、搜索和 AgentScope。
- Trace 记录 workflow/version、工具事件、证据引用、终态和有界错误码。
- Provider egress 在外发前登记最小化审计事件，普通日志不写用户正文、音频、图片或密钥。
- 管理端只查看聚合统计；真实 Bad Case 需去标识化并人工审核后才能进入 Eval。

## 10. 模块扩展契约

`apps/api/src/gerclaw_api/modules` 中每个实际模块都带有 `AGENTS.md` 和 README。修改模块前应先阅读两份文件，其中定义：

1. 当前 Protocol、实现、消费者和错误语义。
2. 可以安全扩展的方向和所需 schema/migration 同步。
3. 不可破坏的身份、版本、数据最小化、授权和终态约束。
4. 单元、集成、并发与性能验收标准。

新增领域能力应先定义 versioned contract，再实现 module 和 service 编排，最后接入 route、BFF 与前端消费者。不得通过复制前端、建立平行业务客户端或在组件中直接调用 Provider 扩展系统。

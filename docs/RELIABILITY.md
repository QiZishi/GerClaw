# RELIABILITY.md

> 可靠性规范 | 基于PRD.md第6节和第10节生成

---

## 1. 超时策略

| 场景 | 超时时间 | 说明 |
|------|---------|------|
| LLM单候选 API/完整流 | ≤300s（默认180s） | 使用独立 `GERCLAW_AGENT_MODEL_TIMEOUT_SECONDS`；首 token 或持续心跳均不能绕过完整 stream deadline，无公开输出时才切换备用模型。五大处方另有独立的整流程预算 `GERCLAW_PRESCRIPTION_GENERATION_TIMEOUT_SECONDS`（默认600s） |
| LLM单次输出 | ≤32768 tokens（默认32768） | `GERCLAW_AGENT_MODEL_MAX_OUTPUT_TOKENS` 配置 schema 拒绝大于 32768，并同时下发到 OpenAI/DashScope/Anthropic AgentScope adapter；流式输出另受 `GERCLAW_AGENT_MAX_OUTPUT_CHARACTERS`（默认131072）硬上限保护 |
| ASR语音识别 | 30s | 音频上传到识别完成，含网络传输 |
| TTS语音合成（首包） | 10s | TTS流式首包等待10s |
| 联网搜索（AnySearch） | 10s（可配置） | 瞬态失败最多重试一次，再切换 Tavily |
| 联网搜索（Tavily兜底） | 10s（可配置） | 瞬态失败最多重试一次，仍失败则 fail closed |
| MinerU文档解析 | 60s | 文档上传解析较慢（大文件） |
| 文件上传（整体） | 60s | 含MinerU解析总时长 |
| RAG embedding/rerank | 30s（可配置） | 单次 SiliconFlow HTTP 请求；超时进入有界重试并记录 provider 失败指标 |

## 2. 重试策略

- **可重试错误**：网络超时（TimeoutError/AbortError）、5xx错误、限流429、网络断开(NetworkError)
- **不可重试错误**：4xx错误（除429）、认证失败401/403、参数校验失败400、API Key无效、模型不存在
- **重试次数**：最多2次（不含首次请求，即总共最多3次尝试）
- **退避策略**：指数退避（首次1s，第二次2s）+ 随机抖动±300ms
- **模型重试优先级**：主模型→backup1→backup2（通过环境变量配置）；Router 先依据每个 slot 的服务端 capability 声明过滤图片、工具调用和结构化输出不兼容的候选，全部不兼容时不发生 Provider 外发并稳定失败。只有尚未产生可见文本或工具调用时才切换，已产生公开输出后中断则 fail closed，禁止自动重放。
- **搜索重试**：AnySearch 网络/超时/429/5xx 最多重试1次后切换 Tavily；401/403/其他4xx和 schema 错误不重试、直接切换。Tavily 使用相同上限。
- **幂等性**：GET/查询类请求天然幂等；POST对话请求重试时使用相同的trace_id

## 3. 降级策略

| 依赖故障 | 降级方案 | 用户体验 |
|---------|---------|---------|
| 主LLM模型不可用 | 自动切换backup1模型(qwen-plus)，再不行backup2(claude) | 用户无感知（除非所有模型都不可用），控制台日志记录切换事件 |
| 所有LLM模型不可用 | 显示友好错误："AI服务暂时繁忙，请稍后重试" | 不显示技术错误，提供重试按钮 |
| ASR服务不可用 | 隐藏语音输入按钮，提示"语音识别暂时不可用，请文字输入" | 自动降级为文本输入模式 |
| TTS服务不可用 | 播放按钮显示为禁用状态，hover提示"语音播放暂时不可用" | 不自动播放，不影响文字阅读 |
| AnySearch不可用 | 自动切换Tavily搜索 | 用户无感知 |
| 所有搜索不可用 | `SearchModule` 返回 `SEARCH_UNAVAILABLE`；对话工具结果显式失败，不把模型记忆伪装成最新证据 | 仍可使用当前用户上传资料或已有本地证据；两者也不可用时请求补充资料 |
| MinerU不可用 | 提示"文档解析服务暂时不可用"，图片仍可上传(多模态理解) | 文件上传按钮显示状态 |
| RAG embedding/rerank/Qdrant 不可用 | 没有其他证据入口时返回 `RAG_UNAVAILABLE` 并完成 failed Trace；当前用户上传资料或受治理联网检索可用时继续该独立证据链 | 不回退为模型自身知识、不伪造引用；上传资料仍可被正常解读 |
| Chat 所有医学证据入口均不可用或无法生成有效 citation | 在模型调用前完成一条不带伪造 citation 的补充信息提示，并记录 `evidence_unavailable` 安全决策 | 用户可继续补充上传资料、检查结果、用药清单或问题背景；对话不以失败中断 |
| Chat session 已有进行中 turn | Redis lease 拒绝竞争者并返回 `CHAT_SESSION_BUSY` | 提示等待当前回复；不得终止原 turn 或污染原 Trace |
| Memory 抽取/向量/一致性服务不可用 | fail closed 为 `CHAT_MEMORY_UNAVAILABLE`，回滚本轮画像/事实/assistant/成功 Trace | 已提交 user message保留供重试；不发送 `done`、不使用 stale 或未确认画像 |
| 模型在公开流中断 | 返回 `CHAT_MODEL_STREAM_INTERRUPTED`，不切换模型、不持久化伪完成消息 | 已显示内容标为中断，用户使用新 Trace 明确重试 |
| 命中红旗症状 | 在 RAG/模型前确定性短路并发送固定 120/急诊提示 | 不等待在线生成，不产生模型扩写、工具卡或伪造引用 |
| 用户主动停止 SSE | 前端发送 identity-scoped `POST /chat/{trace_id}/cancel`，保持原 SSE 打开直到服务端完成工具/Trace 清理并返回 `cancelled` | 保留片段但明确“未完成且未通过最终校验”，所有 running 工具转为 cancelled，只展示重新生成 |
| localStorage写满/不可用 | 提示"本地存储空间已满，请导出重要对话后清除历史"，不阻塞新对话 | 新对话可正常进行，只是无法持久化 |
| 网络断开 | 显示离线状态提示，禁用发送按钮，网络恢复后自动可用 | 明确告知离线状态 |

## 4. 熔断策略

- 熔断器触发条件：同一服务连续失败5次 或 30秒内失败率>60%
- 熔断持续时间：30s后进入半开状态
- 半开状态：允许1个请求探测，成功则关闭熔断恢复正常，失败则继续熔断30s
- 熔断期间处理：快速失败，直接走降级路径，不再等待超时
- 熔断范围：每个外部服务（LLM/ASR/TTS/AnySearch/Tavily/MinerU）独立熔断器，互不影响

## 5. 健康检查

### 5.1 端点

MVP为纯前端静态站点，无后端健康检查端点。前端在页面加载时：
- 检测网络连接状态（navigator.onLine + 实际fetch测试）
- 尝试发送一个轻量请求到配置的LLM endpoint（OPTIONS或1-token请求）验证API可用性
- 各服务（ASR/TTS/搜索）在首次使用时才做可用性检测

二阶段FastAPI后端健康检查：
- `/health/live`：存活检查（liveness）— 服务是否在运行，返回200
- `/health/ready`：就绪检查（readiness）— PostgreSQL/Redis/Qdrant/AgentScope/本地知识库、RAG 索引、独立 Memory collection 和 Search 主备配置是否可用，返回200/503；Memory 探针绕过热路径 ready cache，强制复验 schema，并在 collection 被外部删除时有锁重建，禁止缓存误报。Search readiness 不执行计费查询，真实连通性由外部 smoke 与运行指标证明。

### 5.2 检查内容

| 依赖 | 检查方式 | 失败影响 |
|------|---------|---------|
| LLM API | 轻量chat completion请求(1 token) | 显示服务不可用警告，禁用发送 |
| ASR API | 可选：OPTIONS预检请求 | 语音按钮禁用，降级文字输入 |
| TTS API | 可选：OPTIONS预检请求 | 播放按钮禁用 |
| 搜索API | 可选：轻量搜索请求(1 result) | 标注无法联网 |
| MinerU API | 可选：上传极小文本测试 | 文档上传按钮禁用 |
| localStorage | try-catch写入测试 | 提示存储不可用 |

## 6. 容错设计

- **输入容错**：用户输入空消息不发送；超长文本自动截断+提示；粘贴文本自动清洗格式
- **音频容错**：录音失败（无麦克风权限/设备被占用）给出明确提示和解决建议
- **流式中断容错**：SSE 连接中断会取消后端 turn；已接收片段只作为临时 UI 内容并标为未完成，不写入 completed assistant 消息。模型已输出公开内容后发生 provider 中断时禁止跨模型续写。
- **显式取消容错**：用户停止不是浏览器直接断流。BFF 先向当前 Trace 的取消端点发送控制请求，原 SSE 继续消费到 `cancelled`。后端以 tenant/actor/trace 三元组注册 task，Redis TTL 键解决启动竞态，Pub/Sub 跨副本投递，副本内 intent 作为最终 success pre-commit fence；即使 AgentScope/provider 在异步清理中吞掉 task cancellation，也不能提交 replayable assistant 或 completed Trace。
- **急症错误容错**：前端先显示的高风险就医卡和后端固定急症正文不得被后续网络错误覆盖；后端短路后不会再启动可能失败或延迟的 RAG/模型调用。
- **JSON解析容错**：模型返回的结构化数据（处方/评估结果）解析失败时，不崩溃，降级为纯文本展示并提示重新生成
- **Graceful Degradation**：JavaScript加载失败时显示基础HTML文本提示；CSS加载失败时仍可阅读内容
- **错误边界**：React Error Boundary捕获组件渲染错误，不导致整页白屏，显示错误提示和重试按钮
- **限流保护**：外部API返回429时，自动等待Retry-After头指定时间再重试
- **内部入口限流**：二阶段受保护 API 使用 Redis 原子 100 req/min per principal；Redis 不可用时 fail closed，避免绕过保护。
- **有界 Trace**：事件写入使用 event_id 幂等、单 Trace 总量上限；读取使用 cursor 分页，finish 对完整 canonical payload 做幂等校验。
- **Chat Trace 重放**：Trace 以不可变 `start_fingerprint` 校验 actor/session/execution type/请求 payload；completed Trace 只重放已提交的 assistant 响应。正在执行的同 Trace 竞争者若没有 lease，不得把 owner Trace 标记为失败；成功接管时历史装载排除当前 Trace 的 user message，避免重复输入。
- **会话租约 fencing**：PostgreSQL sequence 分配永不回退的 fencing token；Redis value 同时携带随机 owner 与 token，使用 TTL 续租和 compare-and-delete。新 owner 开始执行前先把更高 token 与当前 Trace ID 提交到 session 行；任一成功或失败 terminal write 前，worker 都必须在仍持有 Redis lease 时通过 compare-and-renew，并以 PostgreSQL `SELECT FOR UPDATE` 同时校验 token 与 Trace ID。续租失败仍会取消 owner task，Redis 不可用时 fail closed；失去所有权的旧 worker只能回滚，不能覆盖新 owner 的 Trace 终态。
- **终态事务原子性**：成功路径将 assistant 消息、model/RAG/safety/agent-finish 事件与 completed Trace 在同一 request-scoped `AsyncSession` 中一次 commit。失败路径在 session 行锁和 Redis owner 复验仍成立时，将 `SYSTEM_ERROR`、failed/cancelled Trace 与 Bad Case 一次 commit；任一 terminal write 失败都会 rollback，禁止出现消息、Trace 和 Bad Case 相互矛盾的部分终态。
- **Memory 一致性**：每个用户通过 `health_profiles` 行锁串行画像合并，普通事实按 category/entity HMAC key 去重；重大事件有时间时纳入 `occurred_at`，无时间时纳入 source Trace/evidence hash，既保留多次事件又保证同源重放幂等。事实 revision 单调递增，每次原地更新前先在同一事务写入 `memory_fact_revisions` 加密快照。Qdrant 在数据库 commit 前写入 revision-fenced point；当前 Unit of Work 持有本轮精确 UUIDv5 point IDs，数据库提交失败或回滚时直接按这些 IDs 补偿，检索的 PostgreSQL current-revision allowlist 继续排除无法确认的无 PHI 孤儿点。仅按 fact ID 做泛化维护清理时才 scroll 快照后按显式 point ID 删除，禁止宽 filter 误删并发新 revision。
- **Memory 重放与失败**：completed Trace 重放只读取已加密 assistant，不重新运行 `Mem0Middleware`、结构化抽取或 embedding。任一 middleware/model/vector/schema 失败先 rollback 共享 session，再提交 failed Trace/Bad Case；AgentScope fail-open hook 必须由 adapter 终态复验改为 fail closed。
- **上下文有界化**：每轮只读取有界加密历史；达到 `GERCLAW_MEMORY_CONTEXT_BUDGET_RATIO` 后使用 AgentScope `ContextConfig` 压缩，摘要加密保存且保留原始消息。过敏、当前/停用药物、红旗事件和待确认信息是强制保留字段。
- **SSE 背压与终态**：每连接使用有界队列和 heartbeat；`done` 只在 assistant 消息与 completed Trace 的原子事务提交后发出。客户端断开会取消 producer，避免无人消费时无限堆积。工具终态、`error`/`cancelled` 和队列 sentinel 使用有界强制入队，队列已满或消费者放弃时不会无限等待清理；显式取消先完成 cancelled Trace 原子事务，再公开 `cancelled`，前端收到该事件后才退出 stopping 状态。
- **迁移串行化**：Alembic 由独立一次性部署 job 执行，并使用 PostgreSQL advisory lock；API 副本启动不执行 DDL。
- **RAG 索引串行化与 fencing**：全量/增量同步由独立 `rag-index` one-shot job 执行，API 副本不在启动时 embedding。`CorpusIndexer.sync/index_path` 的生产实例在整个写操作期间持有 PostgreSQL session-level advisory lock；锁连接使用 `NullPool`，第二个进程阻塞等待。asyncpg termination listener 将锁会话与 owner task 做 fail-stop 绑定：连接意外丢失会立即取消活跃 writer，进程退出时 PostgreSQL 自动释放会话锁。取消无法撤回已到达 Qdrant 的远端请求，因此每次锁所有权还生成由 `txid_current()` 与 nonce 构成的唯一 fencing generation，point ID 纳入该 token；旧 late upsert 只能写入独立且不可检索的 staging point，不能覆盖新代。所有 stale generation/已移除文档清理都先 scroll 快照 point IDs，再只删除这批显式 IDs，不使用能匹配未来 points 的宽 filter；索引开始时回收遗留 staging。新 generation 完整后才激活；manifest 核验实际 chunk 序列、`total_chunks` 和 generation ownership，仅用于安全 skip。已撤回语料检测使用独立的全量 source→document ID inventory，覆盖多完整 generation 和 incomplete staging，避免 ambiguous manifest 为空时漏删旧医学证据。stale delete 响应丢失时重试同一批显式 IDs，不回滚已激活新代；若两次清理均不可确认，保留完整新旧代并让 manifest 拒绝 skip，下次同步继续清理。
- **RAG 请求重放**：不在 Trace 中保存 query，只保存用运行时密钥计算的 request fingerprint。相同 Trace ID 重试必须匹配 actor、执行类型和 fingerprint；completed Trace 可安全重新查询但不追加重复 Trace 事件。
- **RAG provider 背压**：embedding 使用有界 batch/concurrency 和共享 TPM 节流；429 触发共享冷却，网络/429/5xx 有界重试，其他 4xx 和 schema/维度错误立即失败。
- **RAG 数据保全**：单文档解析或 provider 失败不删除已存旧版证据；仅当语料文件已从根目录移除时才删除对应文档。
- **Search 有界降级**：每个 Provider 最多2次 HTTP attempt，响应体、结果数、snippet 和提取正文均有硬上限；AnySearch 空结果是成功空集，不触发 Tavily 扩散请求。Search runtime 共享有界连接池但不保存用户状态或正文缓存。
- **Search Trace 与重放**：独立 API 每个 Provider attempt 写入 `search.query` 事件；Chat 将同一 context-local attempt metadata 随成功事务写入 Trace。事件只含 provider/operation/outcome/retry/result_count/duration，不含 query 或正文。独立 API 使用 keyed request fingerprint 校验相同 Trace ID；completed Trace 可重新执行但不追加事件，不同 payload 或并发 running 请求返回 409，failed/cancelled 请求要求新 Trace ID。
- **Skill 持久化与失败语义**：Skill current/revision/session selection 以 PostgreSQL 为事实源，内置包每次启动按版本校验发现；注册、更新和删除使用 revision 乐观并发控制。Markdown/ZIP、模型生成、参数 schema、AgentScope loader 或工具权限任一步失败都 fail closed，不产生半注册版本或伪成功 Trace。
- **访客身份连续性**：浏览器同步生成稳定 visitor ID 并在首个请求头中发送，BFF cookie 随后固化身份，因此同一页面并发首请求也收敛到同一 actor。BFF visitor 签名使用独立长期密钥，FastAPI 以 domain-separated HMAC 稳定派生 actor；短期 JWT 换发保持 actor 不变。JWT 签名密钥与访客身份密钥分离，轮换 JWT 不得使历史 session/Memory/Skill 不可见。
- **Skill SSE 终态**：`Skill` viewer 与下游工具的开始/成功/失败/取消均进入有界公开事件；生产者取消或异常时为每个 active Skill 补发 terminal `tool_result` 并终态化 `skill.execute`。客户端只有收到 `done` 才提交成功 UI，提前断流必须显示 `CHAT_STREAM_INCOMPLETE`；用户主动停止等待服务端 `cancelled` 后再显示重新生成入口，不能用 transport abort 冒充已清理成功。
- **急症 Trace 真实性**：红旗症状确定性短路不调用模型，也不得写入伪造的 `model.call=succeeded`、model slot 或 token 属性；只有实际进入模型链的响应才能生成模型审计事件。
- **内存管理**：长对话时定期清理不可见的历史消息DOM节点，避免内存泄漏；录音数据使用后立即释放

## 7. 可观测性要求

- **前端日志**：使用结构化console日志（开发环境），生产环境仅输出error级别
- **关键指标（前端）**：
  - API调用成功率/失败率
  - 首token延迟(P50/P95)
  - 流式输出完整率
  - 模型切换触发次数
  - 降级触发次数
- **Trace ID**：每个对话生成唯一trace_id，贯穿LLM/搜索/ASR/TTS全链路，便于排查问题
- **用户可见错误**：所有错误提示使用用户能理解的自然语言，不含技术术语
- **错误上报（二阶段）**：二阶段接入错误监控系统（如Sentry），自动收集前端异常
- **RAG 指标（二阶段）**：Prometheus 记录 retrieval 成功/空结果/失败、端到端延迟、embedding/rerank 请求结果与延迟、索引文档处理结果和写入 chunk 数。
- **Agent/Chat 指标（二阶段）**：Prometheus 记录 turn outcome/latency 与各 model slot 的 started/succeeded/failed/failed_partial；Trace 记录 token、工具、citation 和 safety 结果，但不记录自由文本。
- **Memory 指标（二阶段）**：readiness 记录独立 collection 与物理 vector point 数；Trace 记录每轮 fact 变更数、confirmed/pending/inactive 计数、category 和画像版本，不记录健康文本。
- **Search 指标（二阶段）**：Prometheus 记录 search outcome/端到端延迟及 provider+operation 的有限 outcome/延迟；禁止 query、URL 或来源域名作为 label。
- **风险告警指标（二阶段）**：Prometheus 以 `source`、`severity`、`outcome` 三个有限枚举记录创建、去重与确认；禁止患者、告警、量表、会话、题目、答案、指导语和自由文本进入 label。

## 8. 灾难恢复

- 备份策略：MVP纯前端无服务端数据，用户数据在localStorage，重要内容建议用户导出PDF/Markdown备份
- 二阶段数据库：每日自动备份，保留7天；RTO<1h，RPO<15min
- 二阶段恢复流程：Docker容器重启→健康检查通过→流量切换
- 前端回滚：IGA Pages/ModelScope支持版本回滚，发现严重问题可快速回退到上一个部署版本
- API故障应急：所有外部API配置备用方案（主备模型、双搜索），单一服务故障不影响整体可用性

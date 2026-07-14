# RELIABILITY.md

> 可靠性规范 | 基于PRD.md第6节和第10节生成

---

## 1. 超时策略

| 场景 | 超时时间 | 说明 |
|------|---------|------|
| LLM流式对话（首token） | 30s | 等待首token超过30s触发超时，切换备用模型 |
| LLM完整响应 | 120s | 流式输出整体超时120s |
| ASR语音识别 | 30s | 音频上传到识别完成，含网络传输 |
| TTS语音合成（首包） | 10s | TTS流式首包等待10s |
| 联网搜索（AnySearch） | 15s | 搜索请求超时15s后切换Tavily |
| 联网搜索（Tavily兜底） | 15s | Tavily同样超时15s |
| MinerU文档解析 | 60s | 文档上传解析较慢（大文件） |
| 文件上传（整体） | 60s | 含MinerU解析总时长 |
| RAG embedding/rerank | 30s（可配置） | 单次 SiliconFlow HTTP 请求；超时进入有界重试并记录 provider 失败指标 |

## 2. 重试策略

- **可重试错误**：网络超时（TimeoutError/AbortError）、5xx错误、限流429、网络断开(NetworkError)
- **不可重试错误**：4xx错误（除429）、认证失败401/403、参数校验失败400、API Key无效、模型不存在
- **重试次数**：最多2次（不含首次请求，即总共最多3次尝试）
- **退避策略**：指数退避（首次1s，第二次2s）+ 随机抖动±300ms
- **模型重试优先级**：主模型→backup1→backup2（通过环境变量配置）；只有尚未产生可见文本或工具调用时才切换，已产生公开输出后中断则 fail closed，禁止自动重放。
- **搜索重试**：AnySearch超时/失败→直接切换Tavily，不在同一服务上重试
- **幂等性**：GET/查询类请求天然幂等；POST对话请求重试时使用相同的trace_id

## 3. 降级策略

| 依赖故障 | 降级方案 | 用户体验 |
|---------|---------|---------|
| 主LLM模型不可用 | 自动切换backup1模型(qwen-plus)，再不行backup2(claude) | 用户无感知（除非所有模型都不可用），控制台日志记录切换事件 |
| 所有LLM模型不可用 | 显示友好错误："AI服务暂时繁忙，请稍后重试" | 不显示技术错误，提供重试按钮 |
| ASR服务不可用 | 隐藏语音输入按钮，提示"语音识别暂时不可用，请文字输入" | 自动降级为文本输入模式 |
| TTS服务不可用 | 播放按钮显示为禁用状态，hover提示"语音播放暂时不可用" | 不自动播放，不影响文字阅读 |
| AnySearch不可用 | 自动切换Tavily搜索 | 用户无感知 |
| 所有搜索不可用 | AI回复中标注"当前无法联网检索，回答基于模型自身知识，仅供参考" | 明确告知用户未联网 |
| MinerU不可用 | 提示"文档解析服务暂时不可用"，图片仍可上传(多模态理解) | 文件上传按钮显示状态 |
| RAG embedding/rerank/Qdrant 不可用 | fail closed，返回 `RAG_UNAVAILABLE` 并完成 failed Trace | 明确告知本地医学证据暂不可用；不回退为模型自身知识、不伪造引用 |
| Chat 本地医学证据不可用或无法生成有效 citation | 在模型调用和医疗正文前返回 `CHAT_EVIDENCE_UNAVAILABLE`，不写 assistant 消息，failed Trace 自动进入 Bad Case | 明确提示暂时无法基于本地证据生成医学建议 |
| Chat session 已有进行中 turn | Redis lease 拒绝竞争者并返回 `CHAT_SESSION_BUSY` | 提示等待当前回复；不得终止原 turn 或污染原 Trace |
| 模型在公开流中断 | 返回 `CHAT_MODEL_STREAM_INTERRUPTED`，不切换模型、不持久化伪完成消息 | 已显示内容标为中断，用户使用新 Trace 明确重试 |
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
- `/health/ready`：就绪检查（readiness）— PostgreSQL/Redis/Qdrant/AgentScope/本地知识库与 RAG 索引文档数是否一致，返回200/503

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
- **JSON解析容错**：模型返回的结构化数据（处方/评估结果）解析失败时，不崩溃，降级为纯文本展示并提示重新生成
- **Graceful Degradation**：JavaScript加载失败时显示基础HTML文本提示；CSS加载失败时仍可阅读内容
- **错误边界**：React Error Boundary捕获组件渲染错误，不导致整页白屏，显示错误提示和重试按钮
- **限流保护**：外部API返回429时，自动等待Retry-After头指定时间再重试
- **内部入口限流**：二阶段受保护 API 使用 Redis 原子 100 req/min per principal；Redis 不可用时 fail closed，避免绕过保护。
- **有界 Trace**：事件写入使用 event_id 幂等、单 Trace 总量上限；读取使用 cursor 分页，finish 对完整 canonical payload 做幂等校验。
- **Chat Trace 重放**：Trace 以不可变 `start_fingerprint` 校验 actor/session/execution type/请求 payload；completed Trace 只重放已提交的 assistant 响应。正在执行的同 Trace 竞争者若没有 lease，不得把 owner Trace 标记为失败；成功接管时历史装载排除当前 Trace 的 user message，避免重复输入。
- **会话租约 fencing**：PostgreSQL sequence 分配永不回退的 fencing token；Redis value 同时携带随机 owner 与 token，使用 TTL 续租和 compare-and-delete。新 owner 开始执行前先把更高 token 与当前 Trace ID 提交到 session 行；任一成功或失败 terminal write 前，worker 都必须在仍持有 Redis lease 时通过 compare-and-renew，并以 PostgreSQL `SELECT FOR UPDATE` 同时校验 token 与 Trace ID。续租失败仍会取消 owner task，Redis 不可用时 fail closed；失去所有权的旧 worker只能回滚，不能覆盖新 owner 的 Trace 终态。
- **终态事务原子性**：成功路径将 assistant 消息、model/RAG/safety/agent-finish 事件与 completed Trace 在同一 request-scoped `AsyncSession` 中一次 commit。失败路径在 session 行锁和 Redis owner 复验仍成立时，将 `SYSTEM_ERROR`、failed/cancelled Trace 与 Bad Case 一次 commit；任一 terminal write 失败都会 rollback，禁止出现消息、Trace 和 Bad Case 相互矛盾的部分终态。
- **SSE 背压与终态**：每连接使用有界队列和 heartbeat；`done` 只在 assistant 消息与 completed Trace 的原子事务提交后发出。客户端断开会取消 producer，避免无人消费时无限堆积。
- **迁移串行化**：Alembic 由独立一次性部署 job 执行，并使用 PostgreSQL advisory lock；API 副本启动不执行 DDL。
- **RAG 索引串行化与 fencing**：全量/增量同步由独立 `rag-index` one-shot job 执行，API 副本不在启动时 embedding。`CorpusIndexer.sync/index_path` 的生产实例在整个写操作期间持有 PostgreSQL session-level advisory lock；锁连接使用 `NullPool`，第二个进程阻塞等待。asyncpg termination listener 将锁会话与 owner task 做 fail-stop 绑定：连接意外丢失会立即取消活跃 writer，进程退出时 PostgreSQL 自动释放会话锁。取消无法撤回已到达 Qdrant 的远端请求，因此每次锁所有权还生成由 `txid_current()` 与 nonce 构成的唯一 fencing generation，point ID 纳入该 token；旧 late upsert 只能写入独立且不可检索的 staging point，不能覆盖新代。所有 stale generation/已移除文档清理都先 scroll 快照 point IDs，再只删除这批显式 IDs，不使用能匹配未来 points 的宽 filter；索引开始时回收遗留 staging。新 generation 完整后才激活；manifest 核验实际 chunk 序列、`total_chunks` 和 generation ownership，仅用于安全 skip。已撤回语料检测使用独立的全量 source→document ID inventory，覆盖多完整 generation 和 incomplete staging，避免 ambiguous manifest 为空时漏删旧医学证据。stale delete 响应丢失时重试同一批显式 IDs，不回滚已激活新代；若两次清理均不可确认，保留完整新旧代并让 manifest 拒绝 skip，下次同步继续清理。
- **RAG 请求重放**：不在 Trace 中保存 query，只保存用运行时密钥计算的 request fingerprint。相同 Trace ID 重试必须匹配 actor、执行类型和 fingerprint；completed Trace 可安全重新查询但不追加重复 Trace 事件。
- **RAG provider 背压**：embedding 使用有界 batch/concurrency 和共享 TPM 节流；429 触发共享冷却，网络/429/5xx 有界重试，其他 4xx 和 schema/维度错误立即失败。
- **RAG 数据保全**：单文档解析或 provider 失败不删除已存旧版证据；仅当语料文件已从根目录移除时才删除对应文档。
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

## 8. 灾难恢复

- 备份策略：MVP纯前端无服务端数据，用户数据在localStorage，重要内容建议用户导出PDF/Markdown备份
- 二阶段数据库：每日自动备份，保留7天；RTO<1h，RPO<15min
- 二阶段恢复流程：Docker容器重启→健康检查通过→流量切换
- 前端回滚：IGA Pages/ModelScope支持版本回滚，发现严重问题可快速回退到上一个部署版本
- API故障应急：所有外部API配置备用方案（主备模型、双搜索），单一服务故障不影响整体可用性

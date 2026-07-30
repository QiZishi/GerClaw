# Memory

对应设计要求 §4.2.5、§4.8、§14。生产实现以 PostgreSQL 为健康事实权威源，并复用 AgentScope 2.0.4 `Mem0Middleware`、`ContextConfig` 和 `Agent.compress_context()`；没有第二套 ReAct，也不使用 mem0 默认 SQLite/明文向量 payload。

## 数据边界

- `messages.content/metadata`、`sessions.context_summary`、`health_profiles.profile`、`memory_facts.statement/details` 和 `memory_fact_revisions.snapshot` 均使用 AES-256-GCM envelope 加密。
- `memory_facts` 保存当前投影，`memory_fact_revisions` 在每次变更前保存不可变密文快照，旧剂量、状态、来源 Trace 和时间不会因停药或纠正而丢失。
- 用户显式 CRUD 使用同一事实源：新增事实进入 `proposed`；纠正生成新 revision 并暂时退出召回，
  直到再次确认；删除写入带原因的 tombstone 而非物理删除；恢复只能作用于本人拥有的 tombstone，
  并以新 revision 恢复删除前状态。自动模型抽取不得复活已删除事实。
- 普通事实以 category/entity 生成稳定 HMAC dedupe key；重大事件有时间时把 `occurred_at` 纳入 key，无时间时使用 source Trace + evidence hash，因此多次跌倒不会相互覆盖，同一输入重放仍幂等。只有用户原文中可逐字验证的 `evidence_span` 才能进入事实。
- Qdrant `gerclaw_user_memory_v1` 只保存向量、HMAC tenant/user namespace、fact UUID、category/status/revision。严禁保存 statement、evidence、actor ID 或 tenant ID 明文。
- Qdrant point ID 为 `UUIDv5(fact_id, revision)`。检索时用 PostgreSQL 当前 `vector_revision` 生成 allowlist point IDs，再校验 Qdrant revision 与 PostgreSQL revision/status，旧写入、回滚孤儿点和 inactive fact 均不可进入 prompt。

## 每轮执行

1. 从加密 `messages` 只加载当前有效回答版本组成的有界短期历史；全量上下文预检为历史动态分配 token budget。超额时用 AgentScope 医疗摘要压缩，强制保留过敏、当前/停用药物、红旗事件和待确认信息；Provider 不可用时只做确定性原文摘录。加密摘要同时保存 `source_hash` 和严格 projection，相同来源与预算直接复用。
2. 将确认画像作为版本化 `memory-prompt-projection-v1` JSON 放入
   `<untrusted-user-memory>` 背景，而不是 system instruction。投影显式携带
   `governance_track=mutable`；偏好逐项标记 `presentation_only`，其他健康自述逐项标记
   `untrusted_user_context`；每条记录保留 `fact_id/revision/status` 并明确
   `mutability=online_crud`，继续服从新增、更新、停用和删除的在线事实源。投影同时声明不得
   覆盖系统、医疗安全、业务、身份授权、工具许可或 Harness 门禁。内容截断只能跳过完整
   record，并继续尝试后续较短记录，不能产生半截 JSON 或丢失权限标签。
3. `Mem0Middleware(mode="both")` 自动召回并暴露 `search_memory`/`add_memory`；GerClaw async client adapter 将调用映射回同一 `ProductionMemoryModule`。
4. 写入只抽取本轮真实 user message，不从 assistant 回复或工具建议反向造事实。模型投影必须符合严格、显式版本化的 `memory-extraction-model-output-v1`；缺失/旧版本、未知字段或异常 shape 在证据核对和持久化前失败。所有新事实默认进入 `proposed`，只有用户通过 revision-fenced decision 明确确认后才写入向量和画像。否认同样先成为提案；确认后才将对应事实转为 inactive。
5. assistant、事实/画像、`memory.update` Trace 与 completed Trace 在同一 request-scoped PostgreSQL 事务提交。模型、Qdrant、schema 或 ownership 失败均不发送 `done`。

同一 category/entity 的新提案若与 confirmed 版本不一致，当前投影进入
`conflicted`，旧确认版本保存在加密 revision/conflict snapshot 中。冲突期间两边都不
进入 prompt；用户可采用新版本或保留旧版本。含“可能/怀疑/鉴别”等诊断方向的
condition/assessment 不写入长期 Memory。

Qdrant 在 PostgreSQL commit 前可能存在不含 PHI 的孤儿 revision point；authoritative point-ID allowlist 令其不可检索。当前 Unit of Work 在写入前已持有精确 UUIDv5 fenced point IDs，回滚补偿直接删除这些 IDs；只有按 fact ID 做泛化维护清理时才先 scroll 快照 point IDs，禁止宽 filter 误删并发新 revision。

## API

- `GET /api/v1/memory/profile`：`memory:read`，返回当前 actor 的解密画像和事实；未建档 actor 返回空画像。
- `GET /api/v1/memory/facts/{fact_id}/history?limit=10`：`memory:read`，仅返回当前 actor 拥有的、每次变更前保存的不可变版本；跨 actor/tenant 和不存在事实统一 404，不返回当前投影以外的其他事实。
- `POST /api/v1/memory/facts/{fact_id}/decision`：`memory:write`，使用 `expected_revision` 乐观锁确认或拒绝当前 actor 的事实；跨 actor/tenant 统一 404。
- `POST /api/v1/memory/facts`：`memory:write`，以 profile version fence 新增本人事实；结果为
  `proposed`，不能直接获得 confirmed 权限。
- `PATCH /api/v1/memory/facts/{fact_id}`：`memory:write`，以 fact revision fence 纠正文本、有限
  结构化细节、发生时间或访问级别；category/entity 不可借此改写。结构化细节或时间变更必须同时
  提交新的用户原文，实体、值、单位、剂量、频率、反应等必须能在该原文中直接核验，否则稳定返回
  `422 MEMORY_EVIDENCE_MISMATCH`；纠正后回到 `proposed`。
- `DELETE /api/v1/memory/facts/{fact_id}`：`memory:write`，写入可审计 tombstone 并立即退出画像和召回。
- `POST /api/v1/memory/facts/{fact_id}/restore`：`memory:write`，仅恢复本人 tombstone；普通
  `inactive`（例如用户拒绝或明确否认）不能伪装成可恢复删除。
- `PATCH /api/v1/memory/profile/recall`：`memory:write`，使用 profile version 乐观锁开关跨会话召回；关闭后记录仍保留在本人健康档案，但不注入对话。

所有 endpoint 共用 Redis principal 限流。Trace 只记录 fact UUID、category、数量、画像版本和结果，不记录健康文本。

## 维护与演进

**可安全改进。** 可优化抽取器、冲突合并、画像展示、生命周期和受授权医生投影；新事实类别需定义证据来源、确认/拒绝、版本迁移与向量 payload 策略。任何模型抽取改动先以合成否定、他人主体和未绑定实体 case 固定边界。

内容演进使用双轨治理中的 mutable track：`preference` 只能获得 `presentation_only` 权限，其他
健康事实只能作为 `untrusted_user_context`。owner service 必须先完成 tenant/actor/resource
归属查询，再调用治理分类；浏览器不能自报 object kind、authority 或 ownership。Memory 的核心
证据、隔离、加密、状态机、revision、tombstone 和召回机制属于不可在线自改的控制面。

**不可破坏的契约。** 事实与版本必须加密并按 tenant/actor 隔离；只有未过期、
`standard` 且无冲突的 `confirmed` 事实可召回，`proposed`/`pending`/`conflicted`/
`inactive` 均不得自动作为事实。用药、生命体征和评估提案按
`GERCLAW_MEMORY_TRANSIENT_FACT_TTL_DAYS` 设置有效期；restricted 或关闭跨会话
召回时即使已确认也不进入 prompt。不得把原健康文本写入 Qdrant/Trace，且每次决定
必须带 `expected_revision`，不能以最后写入者覆盖。

**性能与回归验收。** 覆盖确认、拒绝、否定、冲突、历史、跨 actor 404、向量 fence 与 revision 冲突；运行 memory extraction case。画像读取在历史增长下记录 p95、解密数和向量过滤命中率；10 并发 decision 必须只有一个 revision 成功。

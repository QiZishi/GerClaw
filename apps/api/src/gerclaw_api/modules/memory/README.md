# Memory

对应设计要求 §4.2.5、§4.8、§14。生产实现以 PostgreSQL 为健康事实权威源，并复用 AgentScope 2.0.4 `Mem0Middleware`、`ContextConfig` 和 `Agent.compress_context()`；没有第二套 ReAct，也不使用 mem0 默认 SQLite/明文向量 payload。

## 数据边界

- `messages.content/metadata`、`sessions.context_summary`、`health_profiles.profile`、`memory_facts.statement/details` 和 `memory_fact_revisions.snapshot` 均使用 AES-256-GCM envelope 加密。
- `memory_facts` 保存当前投影，`memory_fact_revisions` 在每次变更前保存不可变密文快照，旧剂量、状态、来源 Trace 和时间不会因停药或纠正而丢失。
- 普通事实以 category/entity 生成稳定 HMAC dedupe key；重大事件有时间时把 `occurred_at` 纳入 key，无时间时使用 source Trace + evidence hash，因此多次跌倒不会相互覆盖，同一输入重放仍幂等。只有用户原文中可逐字验证的 `evidence_span` 才能进入事实。
- Qdrant `gerclaw_user_memory_v1` 只保存向量、HMAC tenant/user namespace、fact UUID、category/status/revision。严禁保存 statement、evidence、actor ID 或 tenant ID 明文。
- Qdrant point ID 为 `UUIDv5(fact_id, revision)`。检索时用 PostgreSQL 当前 `vector_revision` 生成 allowlist point IDs，再校验 Qdrant revision 与 PostgreSQL revision/status，旧写入、回滚孤儿点和 inactive fact 均不可进入 prompt。

## 每轮执行

1. 从加密 `messages` 加载有界短期历史；超出 token budget 时用 AgentScope 医疗摘要压缩，强制保留过敏、当前/停用药物、红旗事件和待确认信息。
2. 将确认画像和摘要作为 `<untrusted-user-memory>` 背景，而不是 system instruction。
3. `Mem0Middleware(mode="both")` 自动召回并暴露 `search_memory`/`add_memory`；GerClaw async client adapter 将调用映射回同一 `ProductionMemoryModule`。
4. 写入只抽取本轮真实 user message，不从 assistant 回复或工具建议反向造事实。否认按 category/entity 作用域处理；限定频率和双重否定不得错误停用事实，低置信度和不确定冲突进入 pending/inactive。
5. assistant、事实/画像、`memory.update` Trace 与 completed Trace 在同一 request-scoped PostgreSQL 事务提交。模型、Qdrant、schema 或 ownership 失败均不发送 `done`。

Qdrant 在 PostgreSQL commit 前可能存在不含 PHI 的孤儿 revision point；authoritative point-ID allowlist 令其不可检索。当前 Unit of Work 在写入前已持有精确 UUIDv5 fenced point IDs，回滚补偿直接删除这些 IDs；只有按 fact ID 做泛化维护清理时才先 scroll 快照 point IDs，禁止宽 filter 误删并发新 revision。

## API

- `GET /api/v1/memory/profile`：`memory:read`，返回当前 actor 的解密画像和事实；未建档 actor 返回空画像。
- `GET /api/v1/memory/facts/{fact_id}/history?limit=10`：`memory:read`，仅返回当前 actor 拥有的、每次变更前保存的不可变版本；跨 actor/tenant 和不存在事实统一 404，不返回当前投影以外的其他事实。
- `POST /api/v1/memory/facts/{fact_id}/decision`：`memory:write`，使用 `expected_revision` 乐观锁确认或拒绝当前 actor 的事实；跨 actor/tenant 统一 404。

所有 endpoint 共用 Redis principal 限流。Trace 只记录 fact UUID、category、数量、画像版本和结果，不记录健康文本。

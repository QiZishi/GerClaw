# 0015-本地医学知识库 Agentic RAG — 执行计划

> 任务编号：0015 | 创建日期：2026-07-15 | 优先级：P0 | 阶段：二（核心能力）

## 1. 权威要求与现状

- 最高权威 `docs/references/gerclaw设计要求.md` §4.4、§4.7、§10、§14、§16.2 要求使用 BAAI/bge-m3、BAAI/bge-reranker-v2-m3、Qdrant、本地知识库优先、混合检索、可追溯引用和 AgentScope 能力。
- 用户要求根 `.env` 的 `GERCLAW_KNOWLEDGE_BASE_HOST_PATH` 所指本地医学知识库必须真正进入 Agentic RAG，所有调试使用根 `.env` 的真实服务，禁止 mock 成功。
- 当前语料为 436 篇 Markdown、约 43.4 MiB；0014 已提供 Qdrant、Trace、认证、限流、加密和模块 Protocol，但 RAG 仍只有接口。
- AgentScope 2.0.4 `RAGMiddleware(mode="agentic")` 会暴露 `search_knowledge` 工具并调用 `KnowledgeBase.search`；内置 `QdrantStore` 仅提供单 dense vector 搜索，不能完成设计要求中的 dense+关键词混合检索和外部 rerank。

## 2. 技术决策

1. Agent 编排层使用 AgentScope 2.0.4 `RAGMiddleware.Parameters(mode="agentic")`，不另造 ReAct/RAG 中间件。
2. 以实现相同 `KnowledgeBase.search` 契约的 GerClaw adapter 接入 middleware；检索底层使用已有 `qdrant-client` Query API 的 dense+sparse prefetch + RRF，再调用 SiliconFlow rerank。
3. dense embedding 使用根 `.env` 的 `BAAI/bge-m3`；稀疏关键词向量使用稳定哈希的中英文 lexical tokenizer，提供关键词召回且不引入第二套模型框架。
4. Markdown 按标题层级和段落边界切分，目标 256–512 近似 tokens、64 tokens overlap；表格不跨行破坏，图片只保留 alt 文本，脚本/注释等指令载体在索引前清理。
5. 文档与 chunk ID 基于相对路径和内容哈希确定性生成；point ID 额外纳入每次锁所有权的 fencing generation，隔离被取消请求的远端 late commit。同步索引仍通过 manifest 幂等跳过未变化文档、替换变化文档、删除已移除文档。
6. Qdrant 只保存公开医学知识片段和可过滤元数据，不保存用户 PHI；本地绝对路径不进入 payload/API，仅返回相对来源。
7. 索引是独立 one-shot job，不在每个 API 副本启动时执行；API readiness 如实报告索引文档/chunk 状态。

## 3. 实现范围

1. 扩展强类型 RAG DTO、配置和错误模型，约束 query、top_k、filters、metadata、响应大小。
2. 实现 Markdown parser、章节 chunker、元数据提取、prompt-injection 清理和确定性 ID。
3. 实现 AgentScope `EmbeddingModelBase` 兼容的 SiliconFlow BGE-M3 client，包含 schema 校验、超时、有限并发和可重试错误。
4. 实现 SiliconFlow reranker client，校验 index/score/document 对齐并限制候选数量。
5. 实现 Qdrant hybrid store：集合 schema 校验、dense+sparse RRF、payload filter、游标扫描、批量 upsert/delete 和索引统计。
6. 实现增量索引器、CLI/Compose one-shot job，并真实同步 436 篇知识库。
7. 实现 `HybridRAGModule`、AgentScope `HybridKnowledgeBaseAdapter` 和 `RAGMiddleware(mode="agentic")` factory。
8. 增加受 JWT scope、tenant、Redis 限流保护的 retrieve/status API；每次 retrieve 自动记录完整 Trace 和 `rag.retrieve` 审计事件。
9. readiness 增加 RAG collection/index 状态；Prometheus 增加检索、索引、外部模型延迟与错误指标。
10. 更新模块 README、架构/可靠性/安全文档和根 `.env.example`。

## 4. 验收标准

- [x] 436/436 本地 Markdown 均被真实解析并同步至 Qdrant；第二次同步全部跳过且不重复 point。
- [x] Qdrant collection 同时包含 `dense` 与 `lexical` named vectors，并使用 RRF 融合。
- [x] Embedding 与 rerank 均由根 `.env` 的真实 SiliconFlow 服务完成，无 mock、skip 或本地随机向量。
- [x] 至少覆盖跌倒、压疮、焦虑、肌少症、冠心病等代表性真实查询，结果来自对应本地文献且 citation 可回溯到相对文件、章节和 chunk。
- [x] 低相关/空查询、非法 filter、超大请求、Qdrant/模型故障均安全失败，不伪造引用或回退到模型自身知识。
- [x] AgentScope middleware 明确为 `mode="agentic"`，真实 `search_knowledge` tool 调用返回本地知识片段和来源。
- [x] RAG API 的认证、tenant、限流、Trace start/event/finish 和失败 bad case 经真实数据库集成测试验证。
- [x] parser/chunker/lexical/indexer/RAG 核心单测覆盖率 ≥80%；真实 PostgreSQL/Redis/Qdrant 与外部服务测试通过。
- [x] 全量与单文档索引写入口由真实 PostgreSQL advisory lock 跨进程串行化；失败 worker 与同代成功 worker 的并发故障回归不会丢失新代。
- [x] `ruff format --check`、`ruff check`、`mypy`、Bandit、pip-audit、Alembic、Docker build/health、MVP lint/build 全部通过。
- [x] 独立审阅者复现关键链路并给出 PASS 后提交。

## 5. 实测记录（2026-07-15）

- 语料预检：436 documents、18 categories、39,837 chunks、最大 512 approximate tokens、解析失败 0。
- 首次索引：真实 BGE-M3 + Qdrant 写入完成，436 documents / 39,837 chunks；针对 provider 429 增加 450,000 TPM 共享节流后失败 0。
- 幂等同步：`indexed=0, skipped=436, failed=0, chunks_written=0`。
- 代表查询：跌倒、压疮、焦虑、肌少症、冠心病的 top-3 均命中对应本地目录；返回相对文件、章节、chunk 和 rerank score。
- 全真实回归：`91 passed`、0 skipped、一次性全量覆盖率 87.58%；独立审阅分组复测主覆盖率 87.55% 且 4 个 external tests 全通过。覆盖三路 LLM、MiMo ASR/TTS、SiliconFlow embedding/rerank、Tavily、PostgreSQL、Redis、Qdrant、RAG API/Trace replay/failed Bad Case、索引中断/lost-ack/锁断连/远端 late-commit fencing/撤回证据清理和 AgentScope tool。
- Docker HTTP：`/health/ready` 为 200；RAG 状态为 436/436/39,837；真实 retrieve 为 200、3 citations、Trace completed。
- 故障恢复：分批 upsert 第二批中断后旧 generation 仍为 1/2 chunks 完整可检索，新 staging 被清理；复跑成功切换为 1/3 chunks 新 generation。
- lost-ack 恢复：stale delete 已提交但首次响应丢失时，幂等重试保留 1/3 chunks 新代；清理持续失败时新旧代保持可用、manifest 不 skip，依赖恢复后复跑只保留新代。
- 并发写恢复：两个独立 writer 争用同一新版 generation 时由 PostgreSQL session advisory lock 串行执行；首个 writer 第二批失败并清理后，等待中的 writer 完整写入，最终 manifest、stats 与 search 仅保留完整新代。
- 锁会话失效：真实 `pg_terminate_backend` 强制断开持锁连接后，asyncpg termination listener 立即取消仍在 critical section 的 owner task；取消完成后新连接可重新获取锁，避免已失锁 worker 继续执行 Qdrant 写入/共享 ID 清理。
- 远端 late commit fencing：旧 writer 被取消后延迟落地的 staging upsert 使用独立 point IDs，不影响新代 stats/manifest/search；旧 writer 延迟 stale-delete 只含其激活前快照到的显式 IDs，无法删除未来 writer，新同步会回收遗留 incomplete staging。
- 撤回证据清理：cleanup outage 造成同 source 两个完整 generation、safe manifest 为空后删除源文件，下一 sync 仍通过独立全量 inventory 识别 document ID，报告 `deleted=1` 并清空 stats/manifest/search，不再让已撤回医学证据继续命中。
- 长表边界：80 行无标点 Markdown 医学表格的所有 chunk 只在完整行之间切分，表格 chunk 禁用字符级 overlap，无行尾孤片。
- Compose 操作：按 README 的 base+dev 文件组合实际运行 `rag-index`，Qdrant/API 未停止，结果为 436 全部 skipped。
- 独立审阅：第五轮最终 PASS；真实 PostgreSQL 断锁后的 late upsert/stale-delete、legacy manifest、ambiguous manifest 撤回证据、lost-ack 与持续 cleanup 均由审阅者独立复现通过，未发现剩余 P1/P2。

## 6. 明确不在本变更集内

- 不提前实现完整聊天 Agent Harness、Memory、Skill、Voice、处方或 CGA；0015 只交付可被后续 Harness 直接注入的生产级 Agentic RAG 能力。
- 不声称已经达到万级并发；本轮只保证异步批处理、连接池、有界并发和可观测性，系统级容量必须在全链路完成后压测证明。

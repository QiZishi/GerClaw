# RAG

对应设计要求 §4.7，已交付可被后续 Agent Harness 直接注入的 local-first Agentic RAG 模块。

生产检索链路只有一套：

1. `MarkdownMedicalParser` 在知识库根目录边界内解析 UTF-8 Markdown，清理可执行的 HTML/隐藏载体并保留标题、表格和引用信息。
2. `MedicalMarkdownChunker` 按标题层级生成有界 chunk，并用相对路径、内容哈希和位置生成确定性 ID。
3. `SiliconFlowEmbeddingModel` 使用根 `.env` 配置的 `BAAI/bge-m3`；`LexicalEncoder` 产生中英文 sparse vector。
4. `QdrantHybridStore` 使用 dense+sparse prefetch 和 RRF 融合，然后交给 `BAAI/bge-reranker-v2-m3` 真实重排。
5. `HybridKnowledgeBaseAdapter` 将同一条检索链路交给 AgentScope 2.0.4 `RAGMiddleware(mode="agentic")`，对 Agent 暴露 `search_knowledge` 工具。

索引通过 `gerclaw-rag-index` 或 Compose `rag-index` one-shot job 增量同步，不在 API 副本启动时执行。所有 `CorpusIndexer.sync/index_path` 写入口都先获取 PostgreSQL session-level advisory lock，跨容器并发 writer 会阻塞等待；锁使用独立非池化连接，asyncpg termination listener 会在锁连接丢失时立即取消活跃索引 task，worker 退出时 PostgreSQL 自动释放。每次锁所有权都产生唯一 fencing generation，point ID 纳入该 token，使已取消请求的远端 late commit 与下一 writer 物理隔离；stale cleanup 只删除激活前明确 scroll 到的 point IDs，绝不使用可能覆盖未来 generation 的宽 filter。每个新 generation 先 staging，全部 point 成功后才激活；遗留 staging 在下次同步开始时回收。安全 manifest 只负责判断可否 skip，语料撤回另用全量 source/document inventory 检测，即使多完整 generation 使 manifest 为空也会清除已撤回证据。已激活新代不会因 stale-delete lost acknowledgement 被盲目回滚；清理持续失败时 manifest 拒绝幂等 skip，待依赖恢复后再清理旧代。请求查询只返回知识库相对路径、章节、chunk 和分数；Qdrant 与 Trace 都不保存 query、PHI 或 Chain-of-Thought。详细配置、运行命令与实测结果见 `apps/api/README.md`。

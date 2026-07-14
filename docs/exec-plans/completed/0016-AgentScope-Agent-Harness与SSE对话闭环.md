# 0016-AgentScope Agent Harness 与 SSE 对话闭环 — 执行计划

> 任务编号：0016 | 创建日期：2026-07-15 | 优先级：P0 | 阶段：二（核心引擎）
> 完成日期：2026-07-15 | 独立审阅：PASS

## 1. 权威要求与现状

- 最高权威 `docs/references/gerclaw设计要求.md` §4.2、§4.5、§4.6、§4.16、§9、§14、§16.2 要求 AgentScope ReAct、三模型依次兜底、完整 SSE 事件、上下文组装、安全检查和前后端对话协议。
- 用户要求所有模型与 RAG 调试只使用根 `.env` 的真实服务，禁止 mock 成功；密钥不得进入日志、Trace、响应或版本库。
- 0014 已交付 PostgreSQL/Redis/Qdrant、JWT/tenant、加密字段、限流、Trace/Feedback/Bad Case；0015 已交付真实本地医学 Agentic RAG。当前 Agent Harness 仍只有 Protocol，聊天仍由 MVP 的 Next Route 直连模型且本地检索返回维护中空结果。
- AgentScope 2.0.4 已提供 `Agent`、`ReActConfig`、`reply_stream()`、AgentEvent、`RAGMiddleware(mode="agentic")` 与单 fallback 模型；其原生单 fallback 不满足 primary → backup1 → backup2 的完整链路。

## 2. 技术决策

1. ReAct 主循环、工具调度和 Agentic RAG 使用 AgentScope 2.0.4 `Agent`，不自研第二套 ReAct 循环。
2. 在 `ChatModelBase` 边界实现可替换的三模型 failover adapter；仅在尚未输出可见内容时自动切换，避免中途重放产生重复或互相矛盾的医疗文本。切换原因、slot、延迟进入脱敏 Trace，不返回 provider 异常正文。
3. 每次请求构造隔离的 `AgentState(session_id=...)`，从 PostgreSQL 装载有界历史；AgentScope 热状态不作为事实存储。完整 Memory Protocol、长期画像抽取与上下文压缩留给 0017。
4. 会话与消息使用现有加密列持久化；访客也映射为 tenant-scoped pseudonymous user。Redis 分布式租约保证同一会话只有一个 in-flight turn，跨进程重复提交安全失败。
5. `POST /api/v1/chat` 直接返回标准 SSE。内部 `reasoning_summary` 只投影“正在分析/正在检索”等可公开状态；绝不暴露 `ThinkingBlock` 原始 Chain-of-Thought。对前端兼容时可将该安全摘要编码为 `event: thinking`。
6. 医疗请求先通过本地证据门：本地 RAG 提供至少一条可追溯证据后才释放医疗正文；Agent 仍可通过 agentic `search_knowledge` 工具自主追加/改写检索。无证据时明确失败，不回退到模型自有知识伪造医学建议。
7. 文本按句子边界通过安全后处理后再流出，拦截确定性诊断措辞；红旗输入优先发送立即就医提示；每次最终输出强制追加统一免责声明。
8. 模型、工具、SSE、持久化和安全决策全部记录 bounded allowlist Trace metadata；自由文本只进入加密消息列。

## 3. 实现范围

1. 扩展强类型 Chat/SSE DTO、错误类型和 Agent Harness Protocol，所有输入、AgentScope 事件与模型响应跨边界校验。
2. 实现三模型 failover、AgentScope Agent factory、ReAct 配置、RAG middleware 注入和安全事件投影。
3. 实现医疗意图/红旗检测、证据门、引用采集、确定性诊断改写和免责声明后处理。
4. 实现 tenant-scoped user/session/message repository 与 service；保存 user/assistant turn、引用、模型 slot、Trace 关联和安全结果。
5. 实现 Redis session lease，包含唯一 owner token、TTL、原子 compare-and-delete 和冲突错误。
6. 实现 JWT `chat:write` 保护的 `POST /api/v1/chat` SSE route；包含无缓冲头、断开取消、规范化错误帧和 Trace 自动 start/event/finish。
7. 增加会话创建/历史读取的最小 API，使真实客户端无需伪造后端状态即可开始和恢复对话。
8. 增加单元、PostgreSQL/Redis/Qdrant 集成与真实外部端到端测试；真实测试至少覆盖模型回复、RAG 引用、SSE 顺序、消息落库和 Trace 完成。
9. 更新 Agent Harness README、API README、架构/安全/可靠性文档和 `.env.example`，记录安全化 thinking 语义与本里程碑边界。

## 4. 验收标准

- [x] 根 `.env` 三个真实模型均可通过 AgentScope 调用；真实 primary 请求产生逐段 SSE，模型名/密钥/原始错误不泄漏。
- [x] 可控故障测试证明 primary → backup1 → backup2 顺序、触发条件、无可见内容前切换与有可见内容后 fail-closed 语义。
- [x] 真实医疗问题通过 AgentScope Agentic RAG 命中 0015 的本地知识库，最终 `done.references` 可追溯到相对文献、章节和 chunk，消息 metadata 与 Trace citation IDs 对齐。
- [x] 无相关证据、RAG/模型故障、迭代超限、客户端断开和 session 并发冲突均安全失败，不写入伪完成 assistant 消息；失败 Trace 自动形成 Bad Case。
- [x] SSE 顺序覆盖 agent_start → safe thinking/reasoning summary → tool_call/tool_result（如发生）→ text_delta → done；原始 ThinkingBlock、用户文本、工具查询和 PHI 不进入 Trace/日志。
- [x] 医疗输出不含确定性诊断，红旗症状提示立即就医，每次完成输出均含“内容由 AI 生成，仅供参考。身体不适请及时就医。”。
- [x] 访客/账号会话 tenant 与 actor 隔离；历史消息字段在 PostgreSQL 中为密文，API 解密仅返回当前主体数据。
- [x] 同一 session 跨两个 API 实例并发提交只有一个获得 Redis lease；租约 owner 不会误删后来者锁。
- [x] `ruff format --check`、`ruff check`、`mypy`、Bandit、pip-audit、Alembic、全量 pytest、Docker build/health、MVP lint/build 全部通过。
- [x] 独立审阅者复现关键真实链路并给出 PASS 后提交和归档。

## 5. 完成证据

- 默认测试：`137 passed, 19 deselected`，branch coverage `80.08%`；Ruff format/check 与 mypy（65 个源码文件）通过。
- 真实 PostgreSQL/Redis/Qdrant：`151 passed, 5 deselected`，coverage `88.21%`；session lease、数据库 fencing、成功/失败终态原子性和 Agentic RAG 均走真实服务。
- 根 `.env` external：`5 passed in 62.31s`；三套真实 LLM、完整 Chat + 本地 Agentic RAG、SiliconFlow embedding/rerank、Mimo ASR/TTS、Tavily 全部通过，无 mock。
- 本地知识库索引：436 个文档、39,837 chunks；完整 Chat 的 citation、加密消息、Trace、幂等重放一致。
- Alembic 在全新专用库完成 `upgrade head → downgrade base → upgrade head`，最终 `bf1a2d7c2016 (head)`；Bandit、pip-audit、MVP lint/build 和 Docker health 通过。
- 独立审阅者对确定性诊断、引用 fail-closed、事务原子性、Trace 排重、Redis/PostgreSQL TOCTOU、final-only/whitespace-only 输出和 provider client 生命周期完成对抗复审，最终结论 PASS。

## 6. 明确不在本变更集内

- 不实现长期 Memory 画像抽取、自动摘要/压缩、Mem0/ReMe；这些由 0017 在本轮加密会话事实源之上实现。
- 不实现 Search、Skill、Voice、Document、五大处方、CGA 或完整前端迁移；本轮只提供这些模块可依赖的生产 Agent/SSE 核心。
- 不声称已经达到万级并发；本轮落实无共享 AgentState、异步 I/O、连接池和分布式会话互斥，最终容量需在完整链路后用负载测试证明。

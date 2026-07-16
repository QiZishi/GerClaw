# Agent Harness

对应设计要求 §4.2、§4.5、§4.6、§4.16、§9、§14、§16.2。当前实现以 AgentScope 2.0.4 `Agent` + `ReActConfig` 为唯一 ReAct 主循环；每个 turn 创建隔离的 `AgentState`，PostgreSQL 加密会话才是可恢复事实源。

## 执行链路

1. API 根据签名 JWT 派生 tenant/actor；PostgreSQL sequence 为每次租约尝试分配单调 fencing token，Redis owner-token lease 串行化同一 session。
2. 新 owner 先把更高 fencing token 与当前 Trace ID 提交到 session 行，再装载排除当前 Trace 的有界历史；用户消息按 `(tenant_id, trace_id, role)` 幂等落库。
3. 医疗输入先执行本地证据门；检索结果必须能投影为至少一条结构合法、可追溯的本地 citation，才允许调用模型并释放医疗正文。
4. AgentScope 可自主调用 `search_knowledge`；该工具复用 production hybrid RAG，不存在简化检索旁路。
   默认每种检索工具只调用一次；只有首轮无可用证据或存在独立子问题时才允许再调用一次，避免同义检索循环。默认 ReAct 上限为 6，支持通过受校验的 `GERCLAW_AGENT_MAX_REACT_ITERATIONS` 按环境调整。
5. 三模型按 `primary → backup1 → backup2` 切换。只有尚未产生可见文本或工具调用时才允许切换；thinking-only、空字符串和 whitespace-only 都按 `MODEL_EMPTY_RESPONSE` 继续兜底，流中断后 fail closed。
6. 文本按句经过确定性诊断措辞改写，红旗症状先发 120/急诊提示；AgentScope final-only 正文从本 turn 的 AgentState 安全补齐，纯格式空白差异以已发布 SSE 为权威，任何非空白正文分叉 fail closed；完成输出强制追加统一免责声明和本地 citation。
7. 成功与失败终态都在 Redis lease 尚未释放时复验 owner，并以 PostgreSQL session 行锁同时校验 fencing token 与 Trace ID。成功路径原子提交 assistant、审计事件和 completed Trace 后才发送 `done`；失败路径原子提交 SYSTEM_ERROR、failed/cancelled Trace 和 Bad Case。

## SSE 契约

`POST /api/v1/chat` 返回标准 `text/event-stream`：

`agent_start → thinking → tool_call/tool_result（按需）→ text_delta → done`

- `thinking` 只是“正在检索/正在整理”等安全状态，由内部 `reasoning_summary` 投影；绝不发送 `ThinkingBlock` 或原始 Chain-of-Thought。
- `done.references` 是后端验证过的本地知识库 citation；`done` 只在消息和 Trace 已提交后出现。
- 错误统一为 `event: error` 的稳定 `CHAT_*` code，不返回 provider 响应正文、URL、模型真实名称或凭据。
- 队列有界并提供 heartbeat；客户端断开会取消 turn，并将本请求拥有的 Trace 标记为 cancelled。

## 并发与重放

- Redis lease 使用随机 owner token、续租和 compare-and-delete；terminal write 前执行原子 compare-and-renew。PostgreSQL sequence 的单调 token 和 Trace ID 会由 session 行锁二次校验，因此新 owner 接管后，旧 worker 即使尚未收到取消也不能写任何成功或失败终态。
- assistant、成功审计事件与 completed Trace 共用 request-scoped `AsyncSession` 和一次 commit；失败事件、failed/cancelled Trace 与 Bad Case 也在 fencing 校验后一次 commit。任一阶段失败都 rollback，不形成部分终态。
- Trace 保存不可变 `start_fingerprint`。completed 同 Trace/同 payload 返回已加密保存的 assistant 响应，不重新付费调用模型，也不重复写消息和事件。
- 正在执行的同 Trace 重试如果未取得 lease，不得把原 owner 的 Trace 标记为失败；接管 running Trace 时排除已保存的当前 user message，避免模型上下文重复本轮输入。

长期 Memory、Skill、上传文档、CGA、处方和 Voice 上下文尚未接入本 Harness；在对应模块实现前，非空 `loaded_skills`/`uploaded_files` 会明确拒绝，不会静默忽略。

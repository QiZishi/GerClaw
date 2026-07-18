# Agent Harness

对应设计要求 §4.2、§4.5、§4.6、§4.16、§9、§14、§16.2。当前实现以 AgentScope 2.0.4 `Agent` + `ReActConfig` 为唯一 ReAct 主循环；每个 turn 创建隔离的 `AgentState`，PostgreSQL 加密会话才是可恢复事实源。

## 执行链路

1. API 根据签名 JWT 派生 tenant/actor；PostgreSQL sequence 为每次租约尝试分配单调 fencing token，Redis owner-token lease 串行化同一 session。
2. 新 owner 先把更高 fencing token 与当前 Trace ID 提交到 session 行，再装载排除当前 Trace 的有界历史；用户消息按 `(tenant_id, trace_id, role)` 幂等落库。
3. 医疗输入优先执行本地证据检索；医疗结论、风险判断和用药调整必须绑定结构合法、可追溯的证据。证据可以来自本地知识库、受治理联网搜索或当前用户上传的资料/图片；本地无命中时不得阻断对病例图片的正常视觉解读。若所有证据入口均不可用，系统不调用模型或伪造引用，而是完成本轮对话并提示用户补充症状、检查或完整用药资料。
4. AgentScope 可自主调用 `search_knowledge`；该工具复用 production hybrid RAG，不存在简化检索旁路。
   默认每种检索工具只调用一次；只有首轮无可用证据或存在独立子问题时才允许再调用一次，避免同义检索循环。默认 ReAct 上限为 6，支持通过受校验的 `GERCLAW_AGENT_MAX_REACT_ITERATIONS` 按环境调整。
5. 三模型按 `primary → backup1 → backup2` 切换。只有尚未产生可见文本或工具调用时才允许切换；thinking-only、空字符串和 whitespace-only 都按 `MODEL_EMPTY_RESPONSE` 继续兜底，流中断后 fail closed。
6. 文本按句检查直接临床结论是否已有本轮 evidence：无 citation/Runtime evidence marker 时改写为待核验表述；有本地、联网或上传 citation 时保留结论。患者端仅在整段末尾追加一次“结合依据、完整病史与医生或药师复核”的风险提示，医生端不机械改写。红旗症状先发 120/急诊提示；AgentScope final-only 正文从本 turn 的 AgentState 安全补齐，纯格式空白差异以已发布 SSE 为权威，任何非空白正文分叉 fail closed；普通医疗结论强制追加统一免责声明和可追溯 citation，无证据补充提示则明确标记为无证据状态且不伪造 citation。
7. 成功与失败终态都在 Redis lease 尚未释放时复验 owner，并以 PostgreSQL session 行锁同时校验 fencing token 与 Trace ID。成功路径原子提交 assistant、审计事件和 completed Trace 后才发送 `done`；失败路径原子提交 SYSTEM_ERROR、failed/cancelled Trace 和 Bad Case。

## 日常交流的提示语与预算

- 日常诊疗提示语只要求安全、证据和适合受众的表达，不设置回答字数上限，也不要求模型为固定格式或重复自检额外推理；内容完整度由用户问题决定。
- 输出安全由证据绑定、无证据直接结论改写、红旗短路、引用校验和统一免责声明保障，不依赖模型自行复述检查过程。
- ReAct 默认最多 6 轮；每类检索首次默认只调用一次，只有没有可用证据或存在独立子问题时才允许追加一次，防止同义检索循环。

## SSE 契约

`POST /api/v1/chat` 返回标准 `text/event-stream`：

`agent_start → thinking → tool_call/tool_result（按需）→ text_delta → done`

- `thinking` 只是“正在检索/正在整理”等安全状态，由内部 `reasoning_summary` 投影；绝不发送 `ThinkingBlock` 或原始 Chain-of-Thought。
- `done.references` 是后端验证过的本地知识库、联网检索和上传资料 citation；`done` 只在消息和 Trace 已提交后出现。
- 错误统一为 `event: error` 的稳定 `CHAT_*` code，不返回 provider 响应正文、URL、模型真实名称或凭据。
- 队列有界并提供 heartbeat；客户端断开会取消 turn，并将本请求拥有的 Trace 标记为 cancelled。

## 并发与重放

- Redis lease 使用随机 owner token、续租和 compare-and-delete；terminal write 前执行原子 compare-and-renew。PostgreSQL sequence 的单调 token 和 Trace ID 会由 session 行锁二次校验，因此新 owner 接管后，旧 worker 即使尚未收到取消也不能写任何成功或失败终态。
- assistant、成功审计事件与 completed Trace 共用 request-scoped `AsyncSession` 和一次 commit；失败事件、failed/cancelled Trace 与 Bad Case 也在 fencing 校验后一次 commit。任一阶段失败都 rollback，不形成部分终态。
- Trace 保存不可变 `start_fingerprint`。completed 同 Trace/同 payload 返回已加密保存的 assistant 响应，不重新付费调用模型，也不重复写消息和事件。
- 正在执行的同 Trace 重试如果未取得 lease，不得把原 owner 的 Trace 标记为失败；接管 running Trace 时排除已保存的当前 user message，避免模型上下文重复本轮输入。

长期 Memory、Skill 与已解析上传文档已在标准聊天 turn 中接入本 Harness：文档只会在
Document 模块按 tenant、actor、session 验证并限长后作为显式标记的用户输入资料
注入，绝不写入公共知识库。用户明确要求阅读/概述上传资料且不涉及医疗解释时，Harness
会禁用 Memory、RAG、联网和 Skill，并仅以“上传资料”出处标记；一旦问题涉及血压、
检查、用药等医疗解释，上传资料会与本地知识库及受治理联网证据共同进入同一回答链路。
陪伴 workflow 继续拒绝 Skills 和上传资料。CGA、经治理的处方与 Voice 上下文仍未接入
本 Harness。

## 维护与演进

**可安全改进。** 可替换模型 provider、优化检索轮数和 prompt、增加经过评审的只读工具，或改进 SSE 文案；必须保持 `AgentState` request-scoped，并把新工具经 Runtime registry、workflow profile 和依赖注入接入。

**不可破坏的契约。** 不得绕过 Redis lease + PostgreSQL fencing 的双重写入保护；不得把原始 reasoning、provider body、图片 base64 或 PHI 写入 SSE/Trace；`done` 只能在 assistant 消息和 Trace 原子提交后发送。不得把无证据降级为编造 citation 或无条件模型调用。

**性能与回归验收。** 至少运行 Harness、Chat 路由、SSE、取消/重放相关测试及 Ruff/Mypy；真实 Compose 回归须覆盖 SSE 成功、断开取消、同 trace 重放和跨主体隔离。确定性安全短路在最多 10 并发下必须 10/10 终态唯一、0 部分消息；模型/RAG 延迟另记 p50/p95。

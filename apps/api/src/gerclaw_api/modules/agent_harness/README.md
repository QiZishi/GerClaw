# Agent Harness

对应设计要求 §4.2、§4.5、§4.6、§4.16、§9、§14、§16.2。当前实现以 AgentScope 2.0.4 `Agent` + `ReActConfig` 为唯一 ReAct 主循环；每个 turn 创建隔离的 `AgentState`，PostgreSQL 加密会话才是可恢复事实源。

## 组件边界

根包保留公共 facade 与组合入口，组件合同位于：

- `routing`：Quick/Standard/Deep/Emergency 决策合同；
- `planning`：`PlanNode` 与有界动态 DAG；
- `clinical_state`：带 provenance 的临床事实、未知和冲突；
- `context_snapshot`：版本化、限长的一轮上下文；
- `run_lifecycle`：稳定错误与安全文本流原语；
- `evidence`：可核验 evidence/citation 元数据；
- `plugin_runtime`：受治理能力清单与复用结果引用；
- `evolution_governance`：双轨权限分类与候选不可写组件宪章；
- `evolution_signals`：严格去内容化的离线演化信号。

阶段 1 仅激活了 `context_snapshot`、`run_lifecycle` 和统一
`ResolvedHarnessConfig` 的等价迁移；其余合同先建立独立构造和测试边界，后续阶段按门禁注入，
不会与现有 Runtime、Memory、RAG、Search、Skill 或 Workflow 形成重复实现。

## 执行链路

1. API 根据签名 JWT 派生 tenant/actor；PostgreSQL sequence 为每次租约尝试分配单调 fencing token，Redis owner-token lease 串行化同一 session。
2. 新 owner 先把更高 fencing token 与当前 Trace ID 提交到 session 行，再装载排除当前 Trace 且只含可用 turn 的有界历史；用户消息按 `(tenant_id, trace_id, role)` 幂等落库。失败或取消 turn 的用户消息会保留在对话和审计记录中，但 Conversation 与 Memory 两条模型上下文读取路径都会排除该 Trace；早于 AgentRun 创建的失败则由 Trace 终态同样排除。
3. 医疗输入优先执行本地证据检索；医疗结论、风险判断和用药调整尽量绑定结构合法、可追溯的证据。证据可以来自本地知识库、受治理联网搜索或当前用户上传的资料/图片；无命中或检索暂时不可用时不得阻断模型回答，也不得伪造引用，模型应基于当前上下文完成可用说明并保留不确定性与免责声明。
4. 医疗 turn 的 mandatory evidence node 先用用户原始请求完成一次 production hybrid RAG；
   AgentScope 后续若调用 `search_knowledge`，只能读取同一 turn 已冻结的结果，不会用模型改写的查询
   再次检索并把主题漂移证据引入回答。首轮确无可用本地证据时仍可使用受治理 web search。
   默认 ReAct 上限为 6，支持通过受校验的 `GERCLAW_AGENT_MAX_REACT_ITERATIONS` 按环境调整。
5. 三模型按 `primary → backup1 → backup2` 切换。只有尚未产生可见文本或工具调用时才允许切换；thinking-only、空字符串和 whitespace-only 都按 `MODEL_EMPTY_RESPONSE` 继续兜底，流中断后 fail closed。
6. 文本独立执行确定性诊断安全改写，不把 citation 是否存在当作普通回答的交付门槛。患者端仅在整段末尾追加一次“结合依据、完整病史与医生或药师复核”的风险提示，医生端不机械改写。红旗症状先发 120/急诊提示；AgentScope final-only 正文从本 turn 的 AgentState 安全补齐，纯格式空白差异以已发布 SSE 为权威，任何非空白正文分叉 fail closed；普通医疗结论追加统一免责声明，引用可用时展示真实 citation，引用暂不可用时仍保留正文并明确不确定性。
7. 成功与失败终态都在 Redis lease 尚未释放时复验 owner，并以 PostgreSQL session 行锁同时校验 fencing token 与 Trace ID。成功路径原子提交 assistant、审计事件和 completed Trace 后才发送 `done`；失败路径原子提交 SYSTEM_ERROR、failed/cancelled Trace 和 Bad Case。

## 日常交流的提示语与预算

- 日常诊疗提示语只要求安全、证据和适合受众的表达，不设置回答字数上限，也不要求模型为固定格式或重复自检额外推理；内容完整度由用户问题决定。
- 输出安全由确定性诊断措辞处理、证据绑定（有证据时）、红旗短路和统一免责声明保障；证据缺失不会拦截一般回答，也不依赖模型自行复述检查过程。
- ReAct 默认最多 6 轮；本地证据每 turn 只真实检索一次，后续工具调用复用按用户原始请求冻结的结果，防止同义检索循环和模型查询漂移。

## SSE 契约

`POST /api/v1/chat` 返回标准 `text/event-stream`：

`agent_start → thinking → tool_call/tool_result（按需）→ text_delta → done`

- `thinking` 只是“正在检索/正在整理”等安全状态，由内部 `reasoning_summary` 投影；绝不发送 `ThinkingBlock` 或原始 Chain-of-Thought。
- `done.references` 是后端验证过的本地知识库、联网检索和上传资料 citation；`done.model_execution` 只包含实际成功的 Provider adapter 显示名、模型显示名和主备槽位，不包含 endpoint、凭据或原始载荷；`done` 只在消息和 Trace 已提交后出现。
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

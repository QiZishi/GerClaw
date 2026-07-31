# GerClaw Agent Harness 架构与安全边界

> 文档状态：当前实现说明  
> 更新日期：2026-07-27  
> 适用范围：FastAPI + AgentScope Runtime、标准聊天、CGA/陪伴/处方 workflow 的运行时边界

## 1. 文档目的

GerClaw 的核心不是单次 LLM 调用，而是一个围绕老年医学场景构建的 Agent Harness：它负责把身份、会话、证据、Memory、RAG、工具、模型、输出安全和可审计终态组织成一次受约束的 Agent 执行。

本文回答以下问题：

- 现有 Agent Harness 由哪些组件组成，为什么这样设计；
- 每个组件产生了什么实际效果；
- 上下文如何组装、缓存和压缩；
- Memory 与 RAG 如何进入 Agent；
- 工具、模型、外部 Provider 和医疗输出的安全边界在哪里；
- 当前编排是单 Agent ReAct 还是多 Agent 协作；
- 哪些能力已经交付，哪些仍然属于后续治理或业务计划。

本文以生产代码为准，产品目标以 [GerClaw 设计要求](references/gerclaw设计要求.md) 为最高权威。

## 2. 一句话架构结论

GerClaw 当前采用：

> **每轮一个隔离的 AgentScope ReAct Agent，外接 Memory/RAG/Search/Skill 等受治理能力，由 Runtime Permission、Security Evaluation、医疗证据门和 Orchestration 共同约束。**

当前已经形成生产基础的部分包括：

- AgentScope 2.0.4 ReAct 执行循环；
- 三模型主备故障切换；
- request-scoped `AgentState`；
- 加密短期会话、长期健康事实和医疗上下文压缩；
- local-first Agentic RAG；
- 统一 Runtime Tool Registry、权限、预算和 HITL 原语；
- SSE 执行过程投影、取消、重放和 Trace 终态；
- 医疗证据门、红旗短路、诊断措辞防护和统一免责声明；
- 外部模型/Search 的脱敏和 egress 审计。

当前**没有**完成的内容包括：真正的多智能体临床复核、完整医生资质与患者授权治理、统一字段级数据分类注册表、完整数据生命周期治理，以及 Provider-side Prompt Cache。

## 3. 总体执行链路

```text
浏览器
  │ 同源 HTTPS / HttpOnly Cookie / BFF
  ▼
Next.js server-only BFF
  │ Zod 校验、身份绑定、SSE 代理、Provider 隔离
  ▼
FastAPI ChatService
  │ workflow 校验、主体投影、上下文加载、业务依赖注入
  ▼
ChatTurnCoordinator
  │ Trace 幂等、Redis session lease、fencing token、取消/失败终态
  ▼
ProductionAgentHarness
  │ 红旗短路、本地证据预取、AgentScope Agent、SSE 安全投影
  ├── Model Router：primary → backup1 → backup2
  ├── MemoryMiddleware：长期健康事实检索与循证写入
  ├── RAGMiddleware：search_knowledge / local-first medical evidence
  ├── Search Tool：AnySearch → Tavily，联网证据
  ├── Skill：版本化、受控的声明式能力
  └── GovernedToolRegistry：schema、权限、预算、超时、HITL
  ▼
PostgreSQL / Redis / Qdrant / 外部 Provider
```

## 4. Agent Harness 组件设计

### 4.1 `ProductionAgentHarness`：一轮执行的唯一入口

实现位置：[agent_harness/harness.py](../apps/api/src/gerclaw_api/modules/agent_harness/harness.py)

#### 设计

`ProductionAgentHarness` 将一次请求限定为一个 tenant、actor、session、trace 范围，主要负责：

1. 校验执行身份与请求上下文的一致性；
2. 组装历史、画像、压缩摘要、Memory、RAG、Search、Skill 和上传资料；
3. 构造 AgentScope `Agent`、`AgentState`、`Toolkit` 和 middleware；
4. 驱动 ReAct 事件流；
5. 对工具调用、模型输出、证据引用和医疗安全状态做后处理；
6. 产生稳定的 `AgentResponse` 和 `done` 事件。

#### 设计原因

如果由多个业务路由各自拼接 Prompt、调用模型和执行工具，会出现：

- 权限检查旁路；
- 医疗安全规则不一致；
- Trace 无法覆盖完整执行过程；
- 不同入口使用不同的 RAG 或 Memory；
- 失败时出现部分消息或伪成功。

因此 Harness 是 Agent 执行的唯一运行边界，而不是另一个业务数据源。

#### 实际效果

- 标准聊天、工具调用、模型 fallback、证据引用和医疗输出治理经过同一条链路；
- 每轮状态隔离，不使用进程内用户单例；
- `done` 只有在安全处理完成、消息与 Trace 达到终态后才可发送；
- 失败、取消、超时、无证据和模型断流都有明确状态。

### 4.2 AgentScope `Agent` + `ReActConfig`：唯一 Agent 循环

实现位置：[harness.py::_build_agent](../apps/api/src/gerclaw_api/modules/agent_harness/harness.py:1187)

#### 设计

使用 AgentScope 2.0.4 原生：

- `Agent`；
- `ReActConfig`；
- `AgentState`；
- `Toolkit`；
- `RAGMiddleware`；
- `Mem0Middleware`。

默认 ReAct 上限为 6 轮，可由服务端配置调整，但不能由浏览器或模型自行扩大。

#### 设计原因

项目要求优先使用 AgentScope 的 Agent 生命周期、工具调用、RAG Middleware 和 Memory Middleware，避免维护第二套自研 ReAct 循环。自研循环会导致 AgentScope 事件、工具权限和上下文状态出现两套语义。

#### 实际效果

- Agent 的模型、工具、middleware、事件和状态有统一生命周期；
- Agent 可以自主决定是否进一步调用 `search_knowledge`、`search_memory` 或 `web_search`；
- Harness 仍可在 AgentScope 外部施加证据门、预算、权限和医疗安全规则；
- 项目当前是“单 Agent ReAct + 受治理工具”，不是已经完成的多智能体临床协作。

### 4.3 request-scoped `AgentState`：隔离热状态

#### 设计

每个 turn 新建：

```python
AgentState(session_id=session_id, context=state_context)
```

PostgreSQL 中的加密会话消息、画像和摘要是可恢复事实源，AgentScope 内存状态只是这一轮的执行投影。

#### 设计原因

不能把用户上下文放在全局 Agent、全局 Memory client 或进程级 singleton 中，否则容易发生：

- 跨用户上下文串线；
- 多副本之间状态不一致；
- 授权撤回后旧上下文继续可用；
- worker 重启后事实丢失。

#### 实际效果

- 同一进程中并发用户不会共享 Agent 热状态；
- worker 重启后可从 PostgreSQL 重建上下文；
- 运行时上下文与事实存储分离，便于审计和恢复。

### 4.4 上下文组装器：多源、强绑定、显式来源

协议定义在 [agent_harness/protocols.py](../apps/api/src/gerclaw_api/modules/agent_harness/protocols.py:24)。当前 `AgentContext` 包含：

| 上下文来源 | 进入方式 | 设计原因 | 实际效果 |
|---|---|---|---|
| `ExecutionContext` | tenant/actor/session/trace | 把一次执行绑定到服务端主体 | 防止请求身份与 Agent 状态错配 |
| System instructions | 服务端固定 Prompt | 医疗安全不能由用户或模型决定 | 基础行为规则稳定 |
| Tool names | workflow 动态生成 | 不同 workflow 需要不同能力面 | CGA/陪伴可禁用工具 |
| 健康画像 | 加密 PostgreSQL 解密后的受限投影 | 支持个体化但不暴露完整数据库 | 画像可追踪、可版本化 |
| Memory refs | 不透明事实 ID | 连接召回结果与审计 | 引用可回溯，避免直接信任全文 |
| Session summary | 压缩后的加密摘要 | 控制长对话 token 成本 | 跨请求恢复重要背景 |
| Conversation history | 有界短期历史 | 保留近期对话语境 | 防止上下文无限增长 |
| Loaded Skills | 服务端解析后的版本化 Skill | Skill 不是任意 Prompt 注入 | 能记录具体 Skill/version |
| Uploaded files/images | tenant/actor/session 校验后注入 | 患者资料属于私有证据 | 不进入公共 RAG |
| Local/Web evidence | 预取或 Agent 工具结果 | 医疗结论必须有证据 | 引用、分数、来源可审计 |

这些来源不是无差别拼接：Memory、摘要、上传文档、RAG 和网页都被明确标记为不可信背景数据，不能改变 system instruction、工具权限或任务目标。

### 4.5 Model Router：三模型 failover

实现位置：[services/model_router.py](../apps/api/src/gerclaw_api/services/model_router.py:276)

#### 设计

模型链固定为：

```text
primary → backup1 → backup2
```

每个候选模型具有 capability、timeout、结构化输出、工具调用和多模态能力声明。

#### 设计原因

医疗回答不能在已经输出半段内容后切换模型并拼接两个模型的回答，否则会产生重复、冲突或无法审计的文本。

#### 实际效果

- 尚未产生可见文本时允许顺序 fallback；
- 空响应、仅 whitespace、模型调用异常可触发 fallback；
- 已经产生可见文本后发生断流则 fail closed；
- Provider 原始错误、真实模型细节和密钥不进入客户端 Trace。

同时，模型外发前使用独立的 provider-bound message 副本做脱敏，不修改本地 Agent state。

### 4.6 Memory Middleware：长期健康记忆接入

实现位置：[memory/agentscope_adapter.py](../apps/api/src/gerclaw_api/modules/memory/agentscope_adapter.py)

#### 设计

使用 AgentScope `Mem0Middleware(mode="both")`，但注入 GerClaw 自己的异步 client adapter：

- `search` 映射到 GerClaw MemoryModule；
- `add` 只接收当前真实 user message；
- 不使用 mem0 默认 SQLite 或明文向量存储；
- 失败通过 `raise_if_failed()` 阻止医疗 turn 伪成功。

#### 设计原因

项目需要 AgentScope 的 middleware 生命周期和工具语义，但医疗事实必须由 GerClaw 的加密 PostgreSQL、revision 和 tenant/actor 隔离控制。

#### 实际效果

- Agent 可以自主检索用户历史健康事实；
- 助手推断、工具结果和网页文本不会反向写入用户健康事实；
- 事实写入带 evidence span、状态、版本和可审计来源；
- 旧向量和非当前 revision 不会进入 Prompt。

### 4.7 RAG Middleware：Agentic local-first evidence

实现位置：[rag/agentscope_adapter.py](../apps/api/src/gerclaw_api/modules/rag/agentscope_adapter.py)

#### 设计

AgentScope 的 `RAGMiddleware(mode="agentic")` 使用 `HybridKnowledgeBaseAdapter`，但所有查询实际回到同一个生产 `HybridRAGModule`：

```text
Markdown parser
  → bounded chunks
  → BGE-M3 dense vector
  → lexical sparse vector
  → Qdrant hybrid RRF
  → BGE reranker
  → local-rag-evidence-v1 provenance
```

#### 设计原因

AgentScope 内置的基础 Qdrant 搜索无法单独满足 dense+sparse hybrid、rerank、generation fencing 和医学引用 provenance 要求，因此只复用 AgentScope 的 KnowledgeBase/Middleware 接口，底层使用 GerClaw 生产检索链路。

#### 实际效果

- 医疗输入在模型调用前优先进行本地证据预取；
- Agent 可自主追加 `search_knowledge`，但不会绕过生产 RAG；
- 每条引用带 document、chapter、chunk、source type 和分数；
- 无证据时不会退回模型记忆伪造医学建议；
- 患者上传文档不写入公共知识库。

### 4.8 Search Tool：受治理的联网证据

#### 设计

`web_search` 是单独的 Runtime tool：

- AnySearch 主通道；
- Tavily 自动降级；
- query 外发前执行 PHI 脱敏；
- 结果进行 schema、HTTPS、来源权威等级和去重校验；
- 网页内容包装为不可信 evidence；
- `extract_content` 做 SSRF、私网、metadata 地址和资源大小限制。

#### 设计原因

联网内容可能过期、被污染或携带 prompt injection，不能等同于 system instruction，也不能直接替代本地医学证据。

#### 实际效果

- 需要最新指南、药品说明或用户明确要求联网时才启用；
- CGA workflow 禁用联网搜索；
- Search 的 query、正文、用户身份和密钥不进入 Trace；
- 外部服务故障不会伪造搜索成功。

### 4.9 Governed Tool Registry：唯一工具授权边界

实现位置：[runtime/registry.py](../apps/api/src/gerclaw_api/modules/runtime/registry.py)  
权限实现：[runtime/permission.py](../apps/api/src/gerclaw_api/modules/runtime/permission.py)

#### 设计

AgentScope 的原始 Tool 不直接交给 Agent，而是先经过：

1. server-owned capability 注册；
2. security profile admission；
3. 输入 Pydantic schema 和大小校验；
4. Runtime scope/role/tenant/patient 检查；
5. 外部 egress 脱敏证明；
6. 一次性 permission permit；
7. timeout、output limit 和 execution budget；
8. 高风险动作的 HITL approval。

#### 设计原因

Prompt、模型输出和前端 UI 都不能承担授权责任。Agent 只能提出工具调用意图，是否真正执行必须由服务端 Runtime 决定。

#### 实际效果

- 未注册、版本不兼容、无 scope、无患者归属证明的工具默认拒绝；
- 高风险或有副作用动作不能直接执行；
- 工具输入/输出失控、超时或超限时 fail closed；
- 当前聊天链路中的 RAG、Memory、Search 以只读工具为主，HITL 基础原语已具备，临床副作用 executor 仍待具体业务接入。

### 4.10 Security Evaluation：组件构造前的风险门

Agent、Memory、RAG source、Tool 和 Workflow 都绑定 server-owned security profile，要求名称、版本、owner、risk level、network access 和 data class 一致，并检查必需控制项。

#### 设计原因

只在工具调用时检查安全还不够。一个没有证据 provenance、患者 ownership 或 egress redaction 能力的 Agent/Workflow，不应先被构造出来再依赖运行时补救。

#### 实际效果

- 未评审或版本不匹配的 Agent/Tool/Workflow 无法进入运行态；
- PHI workflow 必须具备 patient ownership control；
- 外部网络组件必须具备 egress redaction；
- evidence-backed Agent/RAG 必须具备 evidence provenance。

### 4.11 Medical Safety Guard：确定性输出治理

Harness 在模型前后都执行安全检查：

- 胸痛、呼吸困难、卒中征象、意识障碍、大出血、自伤风险在模型调用前短路；
- 医疗句子按边界缓冲后再流出；
- 确定性诊断措辞被改写为待评估/可能性表述；
- 当前医疗结论没有可追溯证据时不允许直接放行；
- 患者端诊断或用药调整内容追加风险复核提示；
- 完成输出统一追加免责声明；
- 原始 Chain-of-Thought 不通过 SSE，只发送 `reasoning_summary`。

#### 实际效果

安全规则不依赖模型“自觉遵守”，而是由前置短路、Runtime 证据状态、流式后处理和最终状态校验共同执行。

### 4.12 SSE Projection：把内部执行投影为可审阅状态

对外只发送结构化事件：

```text
agent_start
→ reasoning_summary
→ tool_call / tool_result
→ text_delta
→ done
```

事件中可以显示工具名称、状态、耗时、搜索结果摘要和引用，但不显示：

- 原始 Chain-of-Thought；
- Provider 原始错误；
- Prompt；
- 密钥；
- 不必要的 PHI；
- 未经验证的工具结果。

这样既支持前端展示“Agent 正在做什么”，又不把内部推理或敏感数据暴露给浏览器。

### 4.13 `ChatTurnCoordinator`：可靠终态和重放

实现位置：[orchestration/chat_turn.py](../apps/api/src/gerclaw_api/modules/orchestration/chat_turn.py)

#### 设计

该组件不负责 Prompt、模型或医疗业务，只负责一次 turn 的持久化生命周期：

- Trace 幂等；
- Redis session lease；
- fencing token；
- completed response replay；
- cancellation/failure finalization；
- PHI-free operational metrics。

#### 设计原因

长时间模型请求可能遇到浏览器断开、API 重试、多个 worker 竞争、Provider 断流或进程重启。没有独立的生命周期协调器，就可能重复计费、重复写消息或产生两个终态。

#### 实际效果

- 同一 session 同时只有一个 turn owner；
- 已完成 Trace 重试时直接重放已持久化 assistant 响应；
- 旧 worker 失去 fencing 后不能提交新的终态；
- 取消和失败只有在数据库形成终态后才向上层报告。

## 5. 上下文缓存与上下文压缩

### 5.1 当前没有共享 Prompt Cache

项目当前没有实现传统的 Provider-side Prompt Cache，也没有 Redis 共享用户上下文缓存。原因是共享缓存会扩大授权撤回、租户隔离和隐私失效的风险面。

当前存在的“缓存/复用”只有：

| 机制 | 范围 | 作用 | 是否作为事实源 |
|---|---|---|---|
| `AgentState` | 单个 turn | Agent 执行热状态 | 否 |
| Memory `_cached_queries` | 单个 turn-scoped Memory module | 避免同一查询重复召回 | 否 |
| `sessions.context_summary` | PostgreSQL、session 范围 | 保存压缩后的对话上下文 | 是，作为加密摘要事实 |
| readiness cache | 进程内、短 TTL | 减少健康探测开销 | 否 |
| Redis lease | session 协调范围 | 并发互斥和取消 | 否 |

因此，当前设计重点是“可重建上下文”和“安全隔离”，不是 Prompt Cache 命中率优化。

### 5.2 压缩流程

1. 从加密消息表加载有限历史；
2. 调用模型 `count_tokens()`；
3. 未超过 `memory_context_budget_ratio` 时不压缩；
4. 超限时使用 AgentScope `Agent.compress_context()`；
5. 结构化摘要必须保留过敏、用药、红旗事件、待确认问题等医学关键信息；
6. 摘要加密写入 session；
7. 下一轮以不可信背景上下文重新注入；
8. 原始消息仍保留，可用于追溯。

默认配置包括：

- `agent_history_messages=40`；
- `memory_context_budget_ratio=0.55`；
- AgentScope runtime `trigger_ratio=0.85`；
- `reserve_ratio=0.2`。

## 6. Memory 机制

### 6.1 短期 Memory

- 加密 PostgreSQL `messages` 是权威源；
- 按 tenant、actor、session 隔离；
- 读取数量和单条消息大小有界；
- 当前 turn 的 user message 不重复注入历史。

### 6.2 长期健康事实

长期 Memory 不是任意聊天摘要，而是经过 schema 和 evidence 校验的事实：

- `allergy`、`condition`、`medication`、`vital_sign`、`assessment`、`event` 等固定类别；
- 只接受用户原文中的精确 `evidence_span`；
- Assistant 或工具输出不产生事实；
- `confirmed`、`pending`、`inactive` 表示事实生命周期；
- 每次修改前保存加密 revision snapshot；
- 使用 optimistic revision 防止并发覆盖。

### 6.3 语义召回

```text
用户查询
  → BGE-M3 embedding
  → Qdrant HMAC namespace filter
  → fact/revision point candidate
  → PostgreSQL tenant/user/revision/status 校验
  → 解密后的受限事实进入 Agent context
```

Qdrant 不保存健康文本、姓名、手机号、tenant ID 或 actor ID 明文。

## 7. RAG 机制

### 7.1 本地医学 RAG

当前本地知识链路是：

1. 只读取配置的医学 Markdown 根目录；
2. 清理脚本、隐藏 HTML、注释和不可见载体；
3. 按标题层级、段落和表格边界切块；
4. BGE-M3 生成 dense vector；
5. lexical tokenizer 生成 sparse vector；
6. Qdrant dense+sparse prefetch + RRF；
7. BGE reranker 重排；
8. `local-rag-evidence-v1` 校验 provenance；
9. 通过 AgentScope `RAGMiddleware(mode="agentic")` 暴露给 Agent。

### 7.2 证据门

医疗请求默认在模型调用前执行本地证据预取：

- 有本地证据：注入引用并允许 Agent 继续；
- 本地无证据但有上传资料或联网 Search：进入对应受治理证据路径；
- 所有证据入口不可用：不给模型机会凭记忆生成个体化结论，返回补充资料提示；
- 任何不完整 provenance 的结果都不能成为 citation。

## 8. 安全边界总览

### 8.1 身份与所有权

服务端验证并投影：

```text
tenant_id + actor_id + role + scope + patient ownership + session
```

浏览器不能通过参数或 UI 切换获得额外权限。完整医生资质、细粒度患者授权和部分临床工作台仍受 active plan 约束，见 [0025 身份/RBAC/患者授权](exec-plans/active/0025-身份RBAC与患者授权.md)。

### 8.2 工具边界

Runtime 默认拒绝：

- 未注册工具；
- 未知版本；
- 缺少 scope/role；
- 缺少患者归属证明；
- 未脱敏的外部 egress；
- critical action；
- 超时、超限和 schema 不合法的调用。

高风险或副作用动作必须使用幂等 key 和持久化 HITL approval。当前 Runtime 已交付通用原语，但临床副作用恢复 executor 和多智能体临床复核不属于当前基础 Harness 的完成声明。

### 8.3 数据与日志边界

以下内容不应进入普通 Trace、日志、指标或 Qdrant payload：

- 密钥和 token；
- 原始 Chain-of-Thought；
- 不必要的用户正文和 PHI；
- 原始搜索正文；
- 图片 base64；
- Provider 原始错误正文。

模型 Prompt、Search、TTS、ASR 和文档解析均使用目的绑定的外发策略；但统一字段级数据分类、用户同意、保留/删除/备份清除仍未全部完成。

### 8.4 不可信内容边界

Memory、RAG、Search、上传文档、图片和 Skill 内容都当作数据，不是命令：

- 结构化 schema 校验；
- 明确不可信标签；
- 不允许修改 system/tool/permission；
- RAG parser 清理可执行载体；
- Search extract 防 SSRF 和资源耗尽；
- Skill 使用版本与安全模板。

## 9. Workflow 编排

当前由服务端 Workflow Registry 管理：

| Workflow | 能力边界 | 设计效果 |
|---|---|---|
| `standard` | Memory、RAG、Search、Skill、上传资料 | 完整循证老年医学对话 |
| `cga` | 禁用联网搜索 | 评估过程不受外部网页干扰 |
| `companion` | 禁用长期 Memory、RAG、Search、Skill、上传资料 | 情感陪伴与医疗 Agent 隔离 |
| `prescription` | 高风险、证据绑定、审核优先 | 只能产生待复核草案，不直接形成可执行处方 |

Workflow、Agent、Tool 和 RAG source 在构造/注册时都要通过 server-owned Security Evaluation profile。

### 当前是否是多智能体？

不是。当前生产对话主路径是：

```text
一个 GerClaw Agent
  + Memory Middleware
  + RAG Middleware
  + Search Tool
  + Skill
  + Runtime Permission/HITL
```

多智能体临床复核、主 Agent 与复核 Agent 的责任分离，仍需在具体临床 workflow 中单独实现和验收。

## 10. 交付状态与后续缺口

### 已交付

- AgentScope ReAct Harness；
- request-scoped AgentState；
- SSE 安全投影；
- 三模型 fallback；
- 加密短期/长期 Memory；
- AgentScope Memory compression；
- local-first Agentic RAG；
- Runtime Tool Registry、权限、预算和 HITL 原语；
- Trace、lease、fencing、取消和重放；
- 医疗证据门、红旗短路、诊断措辞和免责声明；
- Search/Model 外发脱敏和部分 egress 审计。

### 仍在进行或不属于当前 Harness 完成声明

- 完整医生资质和患者授权治理；
- 字段级数据分类注册表；
- 用户同意、用途透明、保留、删除和备份清除；
- MinerU、遗留 BFF 和其他 Provider 的统一 egress 台账；
- 临床副作用恢复 executor；
- 多智能体临床复核；
- Provider-side Prompt Cache；
- 万级并发的系统容量证明。

## 11. 相关实现与文档

- [Agent Harness 模块说明](../apps/api/src/gerclaw_api/modules/agent_harness/README.md)
- [Agent Harness 生产实现](../apps/api/src/gerclaw_api/modules/agent_harness/harness.py)
- [Runtime 权限与工具注册](../apps/api/src/gerclaw_api/modules/runtime/README.md)
- [Memory 模块说明](../apps/api/src/gerclaw_api/modules/memory/README.md)
- [RAG 模块说明](../apps/api/src/gerclaw_api/modules/rag/README.md)
- [Orchestration 模块说明](../apps/api/src/gerclaw_api/modules/orchestration/README.md)
- [系统架构](../ARCHITECTURE.md)
- [安全边界](SECURITY.md)
- [生产 Agent Harness 执行计划](exec-plans/completed/0016-AgentScope-Agent-Harness与SSE对话闭环.md)
- [Memory 执行计划](exec-plans/completed/0017-AgentScope-Memory与健康画像.md)
- [RAG 执行计划](exec-plans/completed/0015-本地医学知识库Agentic-RAG.md)
- [Runtime Permission/HITL 执行计划](exec-plans/completed/0021-Runtime-Permission-HITL-Tool-Registry与复核.md)

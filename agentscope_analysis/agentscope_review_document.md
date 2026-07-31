# GerClaw 后端 AgentScope 实现审查报告

## 0. 范围与结论先行

本报告严格基于生产后端源代码和已下载的 AgentScope 2.0.6dev 中文教程进行分析，没有读取项目设计文档，没有修改 `apps/api` 生产代码，也没有执行项目测试、`build` 或 `dev`。

审查对象是 `apps/api/src/gerclaw_api` 下的 297 个 Python 生产源文件（2026-07-31 修订时重新统计；初版为 283 个，代码仍在演进），同时核对了 `requirements.txt`、`apps/api/pyproject.toml`、`apps/api/uv.lock` 和本地虚拟环境中的 AgentScope 实现。

核心结论：

1. AgentScope 已经是 GerClaw 单轮智能体执行链的核心框架，而不是仅仅被用作一个 LLM SDK。`Agent`、`ReActConfig`、`ContextConfig`、`AgentState`、原生事件流、`Toolkit`、`RAGMiddleware`、`Mem0Middleware`、`Skill` 和模型基类均已接入。
2. GerClaw 没有把整个后端改造成 AgentScope 应用。医疗路由、临床安全、患者权限、PHI 外发控制、加密持久化、运行记录、SSE 协议、ASR/TTS、FastAPI API、CGA 和处方业务仍由自有代码负责。
3. 直接导入 AgentScope 的文件有 29 个，共 60 处导入语句（2026-07-31 修订时重新统计；初版为 26 个文件、57 处导入）；这个数量只能说明依赖接入面，不能作为功能占比。真正的 AgentScope 核心路径集中在 `agent_harness`、`runtime`、`rag`、`memory`、`skill` 和模型服务层。
4. 当前生产代码锁定 `agentscope==2.0.4`，而本次教程基线是 `2.0.6dev`。因此，教程中出现的 `TTSMiddleware`、Workspace、Agent Service 等能力只能作为候选方向，不能直接视为当前 2.0.4 环境可无改动使用的 API。

## 1. 教程下载与转换结果

下载范围由目标站点中文导航实际列出的页面确定，共 41 个页面，包含中文首页和所有导航教程页。

| 内容 | 位置 | 数量 |
| --- | --- | ---: |
| 原始 HTML | `agentscope_analysis/tutorial_zh/html/` | 41 |
| 转换后的 Markdown | `agentscope_analysis/tutorial_zh/md/` | 41 |
| 页面路径清单 | `agentscope_analysis/tutorial_zh/page_paths_with_root.txt` | 41 |
| URL、文件映射、HTML SHA-256 | `agentscope_analysis/tutorial_zh/manifest.md` | 41 |

目录按照原始路由镜像保存。例如：

- `building-blocks/agent/configure-agent.html`
- `building-blocks/agent/configure-agent.md`
- `building-blocks/permission-system/permission-rule.md`
- `deploy/agent-service.md`

原始 HTML 总大小约 17.3 MB，转换后 Markdown 总大小约 362 KB。转换内容取页面正文 DOM，保留标题、正文、代码块、代码 Tab、表格、列表、提示框、链接和图片引用；原始 HTML 也完整保留，便于对 Markdown 做回查。`manifest.md` 保存了每个 HTML 的 SHA-256。

## 2. 代码统计与版本基线

### 2.1 直接使用 AgentScope 的代码

| 生产代码区域 | 直接导入 AgentScope 的文件数 | 主要用途 |
| --- | ---: | --- |
| `modules/agent_harness` | 13 | Agent 构造、消息、事件、Toolkit、Skill、工具边界、编排与运行生命周期 |
| `modules/memory` | 2 | AgentScope 上下文压缩、结构化记忆抽取 |
| `modules/prescription` | 2 | `Msg`、`DataBlock`、`StructuredResponse` |
| `modules/rag` | 2 | `KnowledgeBase`、`RAGMiddleware`、Embedding 基类 |
| `modules/runtime` | 2 | AgentScope 工具权限决策封装 |
| `modules/search` | 1 | AgentScope `FunctionTool` 和权限决策 |
| `modules/skill` | 5 | `Skill`、`LocalSkillLoader`、Toolkit Skill viewer |
| `services` | 2 | AgentScope 模型和模型路由封装 |
| **合计** | **29** | **60 处直接导入语句** |

版本依据：

- `requirements.txt:4`：`agentscope==2.0.4`
- `apps/api/pyproject.toml:8`：`agentscope[rag,service,storage]==2.0.4`
- `apps/api/src/gerclaw_api/config.py:277`：默认要求版本 `2.0.4`（初版审计时为 `:271`，代码演进导致行号偏移）
- `apps/api/.venv` 中实际导入版本：`2.0.4`
- 本次下载教程路径：`https://docs.agentscope.io/versions/2.0.6dev/zh`

### 2.2 判断标准

本报告将功能分成三类：

- **原生接入**：生产代码直接构造、继承或调用 AgentScope 对象，例如 `Agent`、`Toolkit`、`RAGMiddleware`。
- **适配接入**：GerClaw 自己实现外层协议，但把 AgentScope 对象作为内部执行接口，例如自定义 `KnowledgeBase` 适配器、Mem0 客户端适配器、权限代理工具。
- **自有实现**：源代码没有使用对应 AgentScope API，功能由 GerClaw 的 FastAPI、Pydantic、数据库、HTTP、规则或领域代码完成。

## 3. 已经按照 AgentScope 代码实现的部分

### 3.1 Agent 构造和 ReAct 执行链：原生接入，程度最高

`modules/agent_harness/planning/agent_factory.py:9-14` 直接导入 `Agent`、`ContextConfig`、`ReActConfig`、`AgentState`、`Toolkit`、`Mem0Middleware` 和 `RAGMiddleware`。

`ProductionAgentFactory.build()`（`agent_factory.py:63-125`）按 AgentScope 的构造模型组装：

- 使用 AgentScope `Agent` 作为请求级智能体；
- 使用 `AgentState` 保存会话级状态；
- 使用 `ContextConfig` 设置上下文压缩阈值和保留比例；
- 使用 `ReActConfig` 设置最大迭代次数、拒绝后停止、外部执行中断行为；
- 通过 `Toolkit` 注入工具；
- 根据文档型请求、陪伴模式和检索开关装配原生 middleware。

这部分不是简单地把 AgentScope 当成模型客户端，而是采用了 AgentScope 2.x 的 Agent + State + Middleware + ReAct 组合方式。GerClaw 在其上添加了老年医学系统提示词、高风险症状提示、上传资料边界和证据要求。

### 3.2 消息、事件和流式生命周期：原生事件接入，外层协议自有

`modules/agent_harness/run_lifecycle/agent_stream.py:13-26` 使用 AgentScope 的 `ModelCallStart/End`、`TextBlockDeltaEvent`、`ToolCallStart/Delta`、`ToolResultEnd`、`RequireUserConfirmEvent`、`RequireExternalExecutionEvent` 和 `ExceedMaxItersEvent`。

`project_agent_stream()`（`agent_stream.py:115-330`）通过 `agent.reply_stream()` 消费原生事件，再映射为 GerClaw 自己的 SSE 事件。由此可见：

- AgentScope 负责 ReAct 内部的模型调用、工具调用和增量事件；
- GerClaw 负责事件过滤、文本长度上限、错误映射、最终消息一致性检查、Memory 失败检查、trace 记录和前端 SSE 结构。

这是“AgentScope 内核 + GerClaw 运行时外壳”的典型适配方式。

### 3.3 Toolkit、ToolBase 和工具代理：原生工具抽象 + 自有治理

`modules/agent_harness/plugin_runtime/production.py:43-121` 使用 AgentScope `ToolBase` 和 `Toolkit`；`plugin_runtime/contracts.py:130-151` 明确把工具端口定义为 `ToolBase`，并说明会构造带权限的 AgentScope tool proxy。

`modules/agent_harness/plugin_runtime/turn_toolkit.py:37-105` 的流程是：

1. 从 `RAGMiddleware.list_tools()` 和 `Mem0Middleware.list_tools()` 获取 AgentScope 工具；
2. 组装 GerClaw 的 Web Search 工具、知识检索工具、记忆工具和 Skill；
3. 用自有注册表做权限包装；
4. 最后交给 AgentScope `Toolkit`。

因此，工具的 schema、调用、结果块和工具列表遵循 AgentScope；工具是否允许调用、是否需要患者授权、是否能产生外发行为，则由 GerClaw 接管。

### 3.4 RAG：AgentScope 检索接口已接入，索引和医疗检索策略为自有实现

`modules/rag/agentscope_adapter.py:35-120` 实现了一个面向 AgentScope 的 `KnowledgeBase` 适配器：

- 将 AgentScope 的 `TextBlock`、`DataBlock` 查询转换为 GerClaw `RAGModule.retrieve()`；
- 将 GerClaw 结果转换为 AgentScope `VectorSearchResult` 和 `Chunk`；
- 使用 AgentScope `RAGMiddleware.Parameters(mode="agentic")`；
- 将来源、可信度和医疗证据包装在 `<medical-knowledge-evidence>` 边界内。

`modules/rag/providers.py:98-222` 继承 AgentScope `EmbeddingModelBase`，使用 `EmbeddingResponse` 和 `EmbeddingUsage`；这说明 Embedding 的模型协议也采用了 AgentScope 基类。

但 `modules/rag/runtime.py`、`indexer.py`、`module.py` 和 `providers.py` 同时实现了自有的解析、切块、Qdrant 混合检索、RRF、重排、限流、重试、provenance 校验和结果 fencing。它不是照搬 AgentScope 的完整知识库实现，而是“AgentScope 检索入口 + GerClaw 医疗检索后端”。

### 3.5 长期记忆和上下文压缩：原生生命周期 + 自有数据权威

`modules/agent_harness/plugin_runtime/turn_toolkit.py:63-105` 使用 AgentScope `Mem0Middleware(mode="both")`，并把 `GerClawMem0Client` 注入其中。

`modules/memory/agentscope_adapter.py:28-127` 没有直接使用 Mem0 默认数据库，而是实现 AgentScope 所需的异步客户端形状，把检索和写回转到 GerClaw `MemoryModule`。代码注释明确说明：临床数据的加密、权限和证据关系不能交给默认的明文/SQLite 记忆存储。

`modules/memory/compressor.py:12-205` 原生使用 AgentScope `Agent`、`ContextConfig`、`AgentState` 和 `compress_context()`，并在外层增加 `MedicalContextSummary` schema、医学字段约束、证据保留规则和确定性 fallback。

所以当前实现保留了 AgentScope 的 middleware 和 context compression 能力，但数据库事实源、加密存储、记忆提取审查、证据链和失败策略均由 GerClaw 控制。

### 3.6 Skill：原生 Skill 对象和 LocalSkillLoader 已使用

`modules/skill/agentscope_adapter.py:8-38` 把 GerClaw 的版本化 Skill 转换为 AgentScope `Skill`；`modules/skill/registry.py:7-42` 使用 AgentScope `LocalSkillLoader(scan_subdir=True)`；`modules/skill/executor.py:16-45` 使用 AgentScope `Toolkit(skills_or_loaders=...)` 和内置 Skill viewer。

GerClaw 额外实现了数据库版本、会话绑定、frontmatter 校验、ZIP/Markdown 安全检查、Skill 所有权、审批和生成演化。因此 Skill 执行接口按 AgentScope，Skill 生命周期和安全边界按 GerClaw。

### 3.7 模型、Embedding 和结构化输出：采用 AgentScope 类型，供应商治理自有

`services/model_factory.py:6-68` 使用 AgentScope 的 OpenAI、DashScope、Anthropic credential 和模型类创建聊天模型，配置来自 `AgentModelConfig`，没有把 API key、模型名和 URL 写死。

`modules/prescription/generator.py:12-13`、`prescription/intake_extractor.py:10-11`、`modules/memory/extractor.py:12-13` 和 `modules/skill/generator.py:8-9` 使用 AgentScope `Msg`、`DataBlock`、`SystemMsg`、`UserMsg` 和 `StructuredResponse`。

这些地方把 AgentScope 当作消息/模型协议和结构化输出边界；真正的处方字段校验、临床规则、记忆证据清洗和 Skill 安全校验仍是 GerClaw 的 Pydantic/规则代码，而不是交给模型自由决定。

## 4. 没有按 AgentScope 已有代码实现、而是采用其他方法的部分

### 4.1 三槽位模型 failover、能力筛选和 PHI 外发审计

`services/model_router.py:276-648` 自定义 `FailoverChatModel`，支持 primary、backup1、backup2 三个模型槽位，并额外做：

- image/tool/structured-output capability 筛选；
- provider-specific structured output failover；
- prompt 外发前 redaction 和审计；
- 每候选模型总超时；
- 已产生可见输出后 fail-closed，避免中途切换造成重复或拼接错误。

AgentScope 2.0.4 的 `ModelConfig` 可以表达一个 `fallback_model` 和重试参数，但不足以覆盖当前三槽位、能力声明、PHI 审计和流式失败语义。因此这里不是“没有使用 AgentScope 模型”，而是模型编排明显由 GerClaw 自己实现。

### 4.2 权限系统：AgentScope 决策格式被复用，但权威策略是 GerClaw

`modules/runtime/registry.py:58-254` 定义 `GovernedTool(ToolBase)`，复制 AgentScope 工具元数据，调用委托工具的 AgentScope `check_permissions()`，随后交给 `RuntimePermissionEngine`。

`modules/runtime/permission.py:24-128` 自定义了角色、principal、患者访问、scope、外部 egress、敏感级别、幂等和 redaction 规则。只有 GerClaw 自己的检查通过后，才吸收 AgentScope 的 `DENY`、`ASK` 或 `PASSTHROUGH` 决策。

当前没有在 Agent 构造时配置 AgentScope `PermissionMode`、`PermissionRule` 或完整 `PermissionEngine` 规则集。也就是说，GerClaw 复用了 AgentScope 的工具权限协议，但没有把 AgentScope 权限引擎作为医疗授权的主策略源；这是有意的安全分层。

### 4.3 路由、临床编排和 DynamicPlan 是自有确定性系统

`modules/agent_harness/planning/contracts.py:18-86` 定义带依赖关系、预算、checkpoint 和 DAG 校验的 `DynamicPlan`；`planning/planner.py:35-176` 的 `DeterministicPlanner` 根据 route、附件、医疗内容和能力集合生成节点；`planning/execution.py:34-110` 按依赖状态推进节点。

`planning/turn.py:44-143` 进一步把确定性 router、planner、model budget preflight 和 clinical decision 组合起来。

这与 AgentScope 教程中的 Plan 工具不同：AgentScope Plan 主要维护一个可由智能体调用的显式任务清单，而 GerClaw DynamicPlan 是医疗请求的有界 DAG、预算检查和临床 checkpoint。当前没有直接使用 AgentScope Plan 工具。

### 4.4 Web Search 是自有 HTTP/MCP-compatible provider，不是 AgentScope MCPClient

`modules/search/providers.py:138-180` 的 `AnySearchProvider` 自己发 JSON-RPC 2.0 到 `/mcp`；类注释称其为 “MCP-compatible JSON-RPC 2.0 adapter”。

`modules/search/agentscope_adapter.py:32-110` 再把搜索能力包装成 AgentScope `FunctionTool` 和权限决策，并加入 `[W#]`、URL、日期、snippet 和 citation。源代码中没有直接导入 `agentscope.mcp`、`MCPClient` 或 Workspace MCP 管理器。

### 4.5 语音 ASR/TTS 是自有 OpenAI-compatible SSE/PCM16 适配器

`modules/voice/module.py:67-235` 自己创建 `httpx.AsyncClient`，解析 ASR/TTS SSE，校验 base64、PCM16 字节长度、超时和 provider 错误，并在 TTS 外发前调用 `redact_external_tts_text()`。

当前没有使用 AgentScope `TTSModelBase`、内置 TTS model 或 `TTSMiddleware`。因此语音层完全是 GerClaw 自有 provider adapter；外发隐私策略和账户级 provider override 是其主要原因。

实际运行状态（2026-07 末真实调用验证）：外部语音服务当前返回 `VOICE_UNAVAILABLE`（`api/routes/voice.py:68` 等稳定错误码，HTTP 503），前端如实降级显示"语音暂不可用"；这使第 5.1 节"统一 TTS 事件流"候选方向更值得在 Provider 就绪后优先评估。

### 4.6 FastAPI 平台、数据库、临床领域和可观测性不是 AgentScope 代码

以下能力在生产源代码中由 GerClaw 自己实现，未发现对应的 AgentScope runtime/service 直接接入：

- FastAPI 路由、鉴权、RBAC、患者访问 grant、账户配置；
- SQLAlchemy/迁移/加密字段/记忆事实版本/处方草稿/CGA assessment；
- chat session fencing、run journal、resume/regenerate、idempotency、SSE 输出协议；
- 高风险症状短路、医学免责声明、引用绑定、外部 provider egress 审计；
- CGA、五大处方、处方审核、慢病和药物相关确定性业务；
- 统一隐私脱敏与数据分类（`modules/privacy_redaction`）、运行时安全评测基线（`modules/security_evaluation`）；
- 文件上传、文档解析、OCR/图片输入及其安全边界。

这不是“完全没有 AgentScope 参与”：例如 orchestrator 仍以 AgentScope `Msg` 和 `Agent` 为执行核心；但平台外围和医疗领域行为不是 AgentScope 现成实现。

## 5. 哪些功能可以借助 AgentScope 代码实现得更好

以下是调研结论，不是本次任务中的改造计划。

| 优先级 | 候选方向 | AgentScope 能力 | 适合怎样接入 | 不应替代的 GerClaw 能力 |
| --- | --- | --- | --- | --- |
| 高 | 统一 TTS 事件流 | `TTSModelBase`、内置 TTS model、`TTSMiddleware` | 将 MiMo provider 封装为 AgentScope TTS model，或在确认版本后使用内置模型，使文本/音频都走 AgentScope event stream | TTS 前 PHI redaction、账户配置、PCM16 合约、provider 审计 |
| 高 | 统一 Agent 可观测性 | `TracingMiddleware` 及 `on_reply`、`on_model_call`、`on_acting` hooks | 把通用 span、耗时、模型调用和工具调用指标下沉到 middleware，减少 orchestrator 中的重复包裹 | 医疗引用绑定、隐私日志裁剪、GerClaw trace schema |
| 高 | 工具级基础权限 | `PermissionContext`、`PermissionMode`、`PermissionRule`、工具 `check_permissions` | 把低风险工具的 allow/deny/ask 规则作为 GerClaw 自定义权限之后的第二层；统一规则匹配和 ASK 事件 | 患者访问、角色授权、PHI egress、租户隔离必须仍由 GerClaw fail-closed 决定 |
| 中 | Reply 预算控制 | `ReplyBudgetControlMiddleware` | 将单次 reply 的 token/推理成本作为 AgentScope 内层预算，和现有 `ExecutionBudget` 并行 | 总模型槽位、外部请求、SSE deadline 和医疗短路 |
| 中 | 上下文卸载 | AgentScope `offloader` 协议、Workspace offload | 为被压缩历史和被截断工具结果实现一个加密、租户隔离的 GerClaw Offloader；比当前只保留摘要更容易回查原文 | 加密数据库、访问授权、证据保留和可删除性 |
| 中 | 通用任务进度 | AgentScope Plan 工具 | 对非临床的报告生成、资料整理、后台任务显示一个 AgentScope task list 适配层 | 临床 DynamicPlan、预算 DAG、SAVI/C3 checkpoint |
| 低/条件 | 标准 MCP 和 Workspace | AgentScope `MCPClient`、Workspace | 当未来要接入多个外部工具、工作区资源或沙箱时，使用标准 client/lifecycle，减少手写 JSON-RPC | 搜索的 citation、untrusted evidence fencing、外发审计和工具权限代理 |
| 低/条件 | Agent Service | AgentScope `create_app`、storage、message bus、Workspace Manager | 若未来需要标准化多租户 session、队列、workspace 生命周期，可评估外围迁移 | 现有 FastAPI API、数据库迁移、trace/run 语义、医疗授权和产品 API 合约 |

### 5.1 最值得优先评估：TTSMiddleware

当前语音代码已经具备流式 ASR/TTS、PCM16、能力卡片、redaction 和 provider 指标，但实现完全独立。教程中的 `TTSModelBase` 和 `TTSMiddleware` 可以统一模型生命周期与 AgentScope 音频事件，使 Agent 的文本输出和音频输出共享同一条事件链。

建议的边界是：AgentScope 负责 TTS 模型接口、事件和 middleware 生命周期；GerClaw 在进入 TTS 之前继续做文本脱敏，并在离开 provider 后做音频协议、权限和审计检查。不能直接把当前 `MiMoVoiceModule` 替换成默认 TTS model，因为这样可能丢失账户级 URL、API 协议和 PHI 处理。

### 5.2 最值得优先评估：TracingMiddleware 与预算 Middleware

`agent_stream.py` 和 `orchestrator.py` 当前手动处理模型调用、工具调用、SSE、预算和 trace。AgentScope 的 middleware hooks 可以把通用的生命周期观测和单次 reply token budget 集中到 Agent 层，减少不同入口之间的分叉。

但 AgentScope 的预算 middleware 不能自动替代 GerClaw 的完整 `ExecutionBudget`，因为后者还约束工具调用次数、provider egress、总 deadline、临床短路和持久化 checkpoint。适合采用“AgentScope 内层预算 + GerClaw 外层硬上限”。

### 5.3 权限系统适合做“内层规则”，不适合取代医疗授权

当前 `GovernedTool` 已经在 AgentScope `ToolBase` 上做了代理。进一步配置 `PermissionContext` 和 `PermissionRule`，可以让工具名称、参数模式、只读/修改行为的通用规则由 AgentScope 统一处理。

但是患者身份、患者访问授权、跨租户数据、外部模型/搜索/TTS 外发和 PHI redaction 属于 GerClaw 的医疗安全边界，不能由通用 AgentScope `PermissionMode` 单独承担。

### 5.4 RAG、记忆和临床 Plan 不应为了“更 AgentScope”而整体替换

- RAG 已经正确使用 `KnowledgeBase`/`RAGMiddleware` 作为 AgentScope 入口；混合检索、RRF、重排、来源绑定和医疗 evidence fencing 具有领域约束，整体替换为默认向量流程未必更好。
- 记忆已经使用 `Mem0Middleware` 和 AgentScope context compression；加密存储、证据事实、患者范围和 deterministic fallback 不应交给默认 Mem0 存储。
- GerClaw 的 DynamicPlan 是临床预算 DAG，不等同于 AgentScope 的通用任务清单；更合理的是未来为非临床任务增加桥接，而不是替换临床计划。

## 6. 主要差异、风险和采用前提

1. **版本差异**：本报告使用的教程是 2.0.6dev，而运行环境是 2.0.4。任何使用教程中新 API 的改造都需要先验证依赖升级、导入路径、事件模型和 middleware 行为。
2. **协议与安全边界**：AgentScope 的 `ToolBase`、`PermissionDecision`、`KnowledgeBase` 和 middleware 适合做执行协议；患者权限、PHI、临床安全和审计必须继续由 GerClaw 做最终裁决。
3. **流式失败语义**：AgentScope 的普通模型 fallback 不等同于 GerClaw 的“可见输出后禁止切换”规则。若采用 `ModelConfig.fallback_model`，只能覆盖简单模型回退，不能删除当前自定义 `FailoverChatModel` 的 fail-closed 逻辑。
4. **Workspace/Agent Service 的迁移成本**：这些能力同时涉及 session、storage、message bus、workspace、MCP、skill 和调度；它们属于平台层迁移，不是单个 Agent 类替换。
5. **医疗结构化输出边界**：现有处方和记忆代码使用 AgentScope `StructuredResponse` 做抽取和格式化是合理的；CGA 数值、药物规则、风险分级等确定性领域逻辑不应改为模型自由生成。

## 7. 关键源代码证据索引

| 结论 | 源代码证据 |
| --- | --- |
| AgentScope Agent 构造 | `apps/api/src/gerclaw_api/modules/agent_harness/planning/agent_factory.py:9-14,63-125` |
| AgentScope 原生事件流 | `apps/api/src/gerclaw_api/modules/agent_harness/run_lifecycle/agent_stream.py:13-330` |
| AgentScope Toolkit 与工具代理 | `apps/api/src/gerclaw_api/modules/agent_harness/plugin_runtime/production.py:43-121`；`plugin_runtime/contracts.py:130-151` |
| 请求级工具组合 | `apps/api/src/gerclaw_api/modules/agent_harness/plugin_runtime/turn_toolkit.py:37-105` |
| GerClaw 权限代理 | `apps/api/src/gerclaw_api/modules/runtime/registry.py:58-254`；`runtime/permission.py:24-128` |
| AgentScope RAG 适配 | `apps/api/src/gerclaw_api/modules/rag/agentscope_adapter.py:35-120`；`rag/providers.py:98-222` |
| 自有 RAG 后端 | `apps/api/src/gerclaw_api/modules/rag/runtime.py`；`rag/indexer.py`；`rag/module.py` |
| Mem0 与上下文压缩 | `apps/api/src/gerclaw_api/modules/memory/agentscope_adapter.py:28-127`；`memory/compressor.py:12-205` |
| Skill 接入 | `apps/api/src/gerclaw_api/modules/skill/agentscope_adapter.py:8-38`；`skill/registry.py:7-42`；`skill/executor.py:16-45` |
| 模型构造与三槽位 failover | `apps/api/src/gerclaw_api/services/model_factory.py:6-68`；`services/model_router.py:276-648` |
| 自有 DynamicPlan | `apps/api/src/gerclaw_api/modules/agent_harness/planning/contracts.py:18-86`；`planning/planner.py:35-176`；`planning/execution.py:34-110` |
| 自有 MCP-compatible Search | `apps/api/src/gerclaw_api/modules/search/providers.py:138-180`；`search/agentscope_adapter.py:32-110` |
| 自有 ASR/TTS | `apps/api/src/gerclaw_api/modules/voice/module.py:67-235` |
| 生产版本锁定 | `requirements.txt:4`；`apps/api/pyproject.toml:8`；`apps/api/src/gerclaw_api/config.py:277` |

## 8. 最终判定

GerClaw 当前采取的是一种清晰的混合架构：AgentScope 负责 Agent 的模型驱动执行、ReAct、工具、事件、middleware、RAG/记忆/Skill 适配和结构化消息；GerClaw 负责医疗产品真正需要的确定性编排、安全治理、数据权威、外部 egress、临床领域逻辑和平台运行时。

因此，不能把当前后端概括为“完全按 AgentScope 实现”，也不能概括为“只调用了 AgentScope 模型”。更准确的结论是：**核心智能体执行层已较深地遵循 AgentScope；医疗安全和生产平台层有意采用自有实现；下一步最有价值的 AgentScope 复用点是 TTS/事件、Tracing/预算、工具级规则权限和加密 Offloader，而不是替换现有临床 RAG、记忆和 DynamicPlan。**

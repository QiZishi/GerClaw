<!-- 来源：https://docs.agentscope.io/versions/2.0.6dev/zh/release-notes -->

# 更新日志

> **提示** 如需查看完整的提交历史与贡献者名单，请访问 [GitHub Releases 页面](https://github.com/agentscope-ai/agentscope/releases)。

## v2.0.5

*发布于 2026-07-23。*

> **提示** **Highlight**：本次版本新增了
>
> - 智能体的结构化输出与运行时状态注入能力，
> - 四种新的工作区后端（OpenSandbox、Daytona、Kubernetes、Bubblewrap），
> - MongoDB / Elasticsearch 向量存储，以及 Word 和 Excel 解析器，以及
> - Agent Service 中基于 SQLAlchemy 的存储后端与跨用户资源共享能力。

### 新增

**Agent 核心（SDK）**

- 支持结构化输出：通过 Agent.reply() Agent.reply_stream() structured_schema structured_output #2150
- 支持运行时状态注入：在每次推理前，将当前时间、计划任务数量与上下文用量以 HintBlock injection_config InjectionConfig #2134

**Workspace**

- 新增 OpenSandboxWorkspace OpenSandboxBackend OpenSandboxWorkspaceManager OpenSandbox #1953
- 新增 DaytonaWorkspace DaytonaBackend DaytonaWorkspaceManager Daytona #1943
- 新增 K8sWorkspace K8sBackend K8sWorkspaceManager #1933
- 新增 BubblewrapWorkspace BubblewrapBackend BubblewrapWorkspaceManager #2051

**Tool**

- 新增内置 PowerShell #2132

**RAG**

- 新增 MongoDBStore #2008
- 新增 ElasticsearchStore #2129
- 新增 WordParser ExcelParser #2025 #2026

**Agent Service**

- 新增 AsyncSQLAlchemyStorage #2029
- 支持以用户组或组织为单位，在不同用户之间共享凭证、智能体与知识库，底层由新增的资源访问策略层实现。( #1998
- 支持将回复过程中的错误暴露给前端，避免静默失败。( #2133

**Model**

- MoonshotChatModel #2141
- 为 DashScopeChatModel qwen3.7-plus deepseek-v4-pro glm-5.2 #2073

**TTS**

- 新增 GeminiTTSModel #1879

**WebUI**

- 对话页面新增回到底部按钮。( #2106

### 变更

**提示词**

- 优化工作区、上下文压缩与 TaskCreate #2111

**WebUI**

- 重构文本输入组件。( #2102
- 重构工具调用的渲染逻辑。( #2072

**Dependencies**

- 重新整理 pyproject.toml #2157
- 将 mcp #2091

### 修复

**Agent**

- 当模型仅返回思考内容时，继续执行推理-行动循环，而不是直接结束本次回复。( #2120
- 单次推理产生多个工具调用时，上下文压缩过程中保持工具调用与工具结果的配对关系。( #2093

**权限系统**

- 统一权限引擎中各权限模式的判定逻辑，并将批量确认的豁免结果传递给后续的工具调用。( #2117

**Model**

- OpenAI 对话模型改用 max_completion_tokens max_tokens #2065
- 通过 OpenAI Responses API 重放对话时，保留原有的推理（reasoning）内容。( #2071

**Formatter**

- 在 Anthropic 消息的往返转换中保留 redacted_thinking #2139
- 丢弃发送给 Anthropic 的空文本块，避免接口报错。( #2007
- 在 Ollama 的工具结果消息中补充 tool_name #2006
- 清理 Gemini 工具 schema 中的 null #2020

**Tool**

- 内置 Bash find -delete -exec #2004

**Skill**

- 加载技能目录时展开用户主目录（ ~ #2053

**Workspace**

- 修复 OpenSandbox 的初始化流程与状态过滤逻辑。( #2046
- 恢复 glob 辅助方法的默认路径。( #2056

**RAG**

- 适配 milvus-lite 3.1.0 的 COSINE 距离语义，修复 MilvusLiteStore #2089

**Agent Service**

- list_messages #2081

**WebUI**

- 修复流式输出或中断过程中 JSON 不完整导致 Read Write Edit #2075
- 新加载的会话自动滚动到底部。( #2100

**文档**

- 修复 tool #2127
- mem0 示例中使用独立的 LLM 实例。( #2078

## v2.0.4

*发布于 2026-07-07。*

> **提示** **Highlight**：本次版本新增了
>
> - 智能体中断能力，
> - 两个长期记忆中间件，以及
> - 在 Team 中邀请已有 Agent 的能力。

### 新增

**Agent 核心（SDK）**

- 支持实时的智能体中断与恢复。( #1995

**Agent Service**

- 新增 POST /sessions/{session_id}/interrupt #1995
- 支持在 WebUI 中中断生成过程。( #1995
- 支持 Team Leader 通过新增的 AgentInvite #1977
- 新增 Session 状态查询端点，用于轮询 Session 生命周期。( #1984

**中间件——长期记忆**

- 新增 AgenticMemoryMiddleware #1927
- 新增 ReMeMiddleware ReMe #1972

**RAG**

- 新增 MilvusLiteStore #1969

**TTS**

- 新增 DashScopeCosyVoiceTTSModel #1866
- 新增 OpenAITTSModel #1878

### 变更

**Workspace**

- 新增 SandboxWorkspaceBase DockerWorkspace E2BWorkspace #1971

**Model**

- ChatModel _call_api ChatResponse ChatModelBase.__call__ #1995

### 修复

**Agent**

- Agent next_handler() #1966
- 修复 ThinkingBlockEndEvent TextBlockStartEvent #1887

**Model**

- 修复 OpenAI Response API 模型及其 Formatter。( #1950
- _sanitize_schema_for_gemini const: value enum: [value] #2016
- ChatModelBase.count_tokens DataBlock #1899

**Formatter**

- Anthropic、Gemini、Ollama 三个 Formatter 现在在解析 ToolCallBlock.input _json_loads_with_repair {} JSONDecodeError #2012
- Gemini Formatter 会在发送前丢弃空的 thinking 块。( #2013

**Tool**

- 内置 Grep head_limit tail_limit #1954

**Credential**

- CredentialFactory.register_credential uvicorn --reload #1964

**文档**

- 修复 agent state tool #1989

## v2.0.3

*发布于 2026-06-19。*

> **提示** **Highlight**：本次版本新增了
>
> - 全新的 rag
> - 基于 mem0 的长期记忆中间件，
> - Token 预算控制中间件，以及
> - ToolBase

### 新增

**Agent 核心（SDK）**

- Agent.compress_context instructions: HintBlock #1942

**Agent Service**

- 在 Team Leader 的 Session 中透出 HITL 事件。( #1918
- 新增内存消息总线，支持单节点部署。( #1925

**中间件**

- 新增 Mem0Middleware #1775
- 新增 BudgetControlMiddleware #1738

**RAG**

- 新增 rag #1926

**Tool**

- 在 ToolBase call() __call__ #1754

**Workspace**

- e2b 与 docker 工作区支持内置工具（ Bash Read Write Edit Glob Grep #1903

**TTS**

- 新增 DashScope CosyVoice 实时 TTS 模型。( #1855

**Model**

- 为 OpenAI Response API 新增 gpt-4o gpt-4o-mini gpt-4.1-nano #1750

**Embedding**

- OpenAI Embedding 模型支持 pass_dimensions #1897

**Utils**

- 支持通过 set_id_factory() uuid4 #1839

**WebUI**

- 渲染 Write Edit #1856
- 新增右侧面板，展示详细的任务与权限上下文，以及已装载的 MCP 与 Skill。( #1945

### 变更

**Message Bus**

- 重构消息总线，将其与 Service 逻辑解耦。( #1923

### 修复

**Model**

- 修正 DashScope 中 qwen max 3.7 的模型 ID。( #1876
- 处理不带 id 的 Gemini function call。( #1883
- 新增 _sanitize_schema_for_gemini #1886

**Formatter**

- AnthropicChatFormatter #1894

**Agent**

- 避免多个 Agent #1906

**Tool**

- 按字节合并 base64 tool response chunk，替代原先的字符串拼接。( #1901

**中间件**

- TTS 音频块使用统一配置的 ID 工厂。( #1930

**App**

- 正确转换 AG-UI SSE 流式事件。( #1917

**Schema**

- 移除 SummarySchema max_length #1891

## v2.0.2

*发布于 2026-06-16。*

### 新增

**Agent 服务与 Team**

- 自定义子智能体模板 #1833
- 自定义 Agent 类 Agent #1838

**Tool**

- Bash

cwd #1822

**Model 与多模态**

- 流式音频 + 实时字幕 #1701

**TTS**

- 全新

tts #1832

**WebUI**

- 凭据侧边栏 #1829
- WebUI 的 CI #1821

### 变更

**Agent 服务基础设施**

- Embedding 模型层重构 _dashscope_embedding.py _dashscope_multimodal_embedding.py embedding/_dashscope/ text-embedding-v3/v4 qwen2.5-vl-embedding qwen3-vl-embedding multimodal-embedding-v1 tongyi-embedding-vision-flash/plus EmbeddingModelCard _embedding.py #1852
- 后台任务管理器重构 message_bus/_base.py _redis_message_bus.py #1849

### 修复

**Model**

- 思考模式下的 tool_choice 回退 tool_choice auto #1830
- Qwen 思考开关 #1774
- Ollama Embedding 客户端 #1836

**Permission 与 Team**

- Workspace MCP 加载器 #1819
- Workspace 根路径 #1823
- Worker Agent 继承 Leader 的权限规则 AgentCreate PermissionContext #1815

**Tool**

- Glob 模式 #1809

**Storage 与 Message Bus**

- Redis 会话 ID #1786
- Redis Message Bus 超时 Bug #1853

**WebUI**

- 修复了侧边栏 group action 中 <button> #1769
- 不可预览的文件附件现在能够正常渲染，并对媒体尺寸做了约束，避免撑破聊天布局。( #1768
- 聊天会话侧边栏在移动端改为浮层抽屉，避免在小屏上抢占空间。( #1772
- 新增了路由级别的错误边界，配套友好的错误页面。( #1828
- 修复了聊天页面的一个渲染 Bug。( #1867
- 修正了中文版引导提示文案中的一处错别字。( #1766

## v2.0.1

*发布于 2026-06-05。*

> **提示** **版本亮点**：**Agent Team** 特性现已在 Agent 服务中支持，可以方便地在一个 Leader 下组合多个子 Agent。

### 新增

**Agent 服务与 Team**

- Agent Team #1776
- 可插拔的工具与中间件 #1709

**Permission**

- 权限系统的整体优化 Edit Write _check_permission _engine.py _decision.py _types.py permission_mode_test.py default explore accept_edits ask #1767

**Model**

- 逐次调用的

client_kwargs #1659
- 15 份主流模型的 YAML 模型卡 claude-opus-4-5 claude-opus-4-6 claude-sonnet-4-5 qwen-max qwen-max-2025-01-25 qwen-turbo qwen-long gpt-4o gpt-4o-mini gpt-4.1-mini gpt-4.1-nano gpt-4.1 gpt-4.1-mini grok-3 grok-3-fast #1731

**RAG**

- rag #1746

**Event**

- EventBase

metadata #1788

**WebUI**

- Fallback 模型 #1699

**Dependencies**

- ripgrep grep #1740

### 变更

**Docs**

- 更新了 README，介绍新的 Agent 服务能力。( #1789

### 修复

**Formatter 与 Model**

- Anthropic Formatter #1668
- 统一的重试逻辑 #1730
- Ollama 与 Gemini thinking_enable=False #1784

**Tool**

- FunctionTool ToolResponse #1703
- 内置

Read #1735
- Bash 子进程窗口 #1717
- Tool Group 的 Skills #1732

**MCP**

- MCPTool 名称 : / #1787

**Workspace 与 Storage**

- LocalWorkspace #1710
- Redis 消息列表 #1734

**WebUI**

- 在当前依赖下前端能够正常构建。( #1708
- Button asChild <button> #1770
- 对话框新增了用于读屏软件的 description，提升无障碍体验。( #1771
- 补全了 Web UI 示例中缺失的文件。( #1661

**Docs**

- 更新了 README 中的钉钉群二维码。( #1662

## v2.0.0

*发布于 2026-05-25。*

> **提示** **版本亮点**：AgentScope 2.0 正式发布！本次发布是一次大规模架构重构 —— Message、Tool、Workspace、Permission、Middleware 与 Service 等核心层全部重写。请参考 [新文档](https://docs.agentscope.io) 了解全新的构建块。

### 新增

**Agent 核心**

- Agent _agent.py #1518
- Agent AgentConfig offload/ storage/ context_compression_test.py #1544
- 工具结果压缩 Agent #1585

**权限系统**

- 全新

tool/_permission/ _engine.py _bash_parser.py _context.py _decision.py _rule.py _types.py #1486

**Tool**

- 基于

ToolBase _bash _edit _glob _grep _read _write _meta _constants #1502
- Task 工具 TaskCreate TaskGet TaskList TaskUpdate Plan #1549
- 工具与 Workspace 集成 Agent #1642

**Workspace**

- 全新

workspace/ _base.py _local_workspace.py offload/_base.py #1586

**Service**

- 基于 FastAPI 的 Agent 服务 #1568

**Middleware 与 Tracing**

- 2.0 中间件机制 Agent middleware/_base.py AgentConfig #1565
- Tracing 作为中间件 middleware/_tracing/ #1633

**Model**

- ChatUsage

cache_creation_input_tokens

cache_input_tokens #1602
- 统一的 thinking tag 处理 <thinking> #1622
- OpenAI 音频输出 #1623
- DashScope 结构化输出 #1651

**Message 与 Event**

- 正式定义

Msg #1454
- Msg

usage #1639

**Scripts**

- 模型调用辅助脚本 scripts/model_examples/ #1604

### 变更

**Message 与 Event**

- 核心构建块简化、

Msg a2a/ a2a_base file_resolver nacos_resolver well_known_resolver formatter/_a2a_formatter.py event/ _event.py #1440

**Tool**

- 工具模块重构 client_base #1493
- Skill Loader 重构 tool/_skill/ _base.py _local_loader.py _skill.py #1513
- tool_choice auto none required tool/_types.py #1524

**Model 与 Formatter**

- Chat 模型实现重构 credential/ _base _anthropic _dashscope _deepseek _gemini _kimi _ollama _openai _xai #1564
- DashScope 兼容 OpenAI #1617
- kimi

moonshot #1609

**MCP**

- 统一的

MCPClient _mcp_client.py _config.py #1572
- MCP 工具注册时会被重命名 #1552
- MCP 单元测试 #1505

**Tracing**

- Tracing 模块迁移至

middleware/_tracing/ _extractor.py _trace.py _converter.py _extractor.py #1579

**Workspace**

- 新增 e2b 与 Docker Workspace examples/web_ui/ #1650

**项目层面**

- 临时弃用 evaluate module rag tts realtime #1438

**Docs**

- 为 2.0 版本更新了 README 与教程。( #1657

### 修复

**Model**

- DashScope

KeyError KeyError #1615
- _format_tools #1635

**Formatter**

- 各 Provider 的 Formatter 与单元测试 #1621
- Moonshot #1653

**MCP**

- MCPTool 输入 Schema 保留

$defs title #1595

**Tool**

- 关闭

.env Write Edit Bash .env #1656

**Scripts**

- 辅助脚本现在会将 TextBlock content #1629

<!-- 来源：https://docs.agentscope.io/versions/2.0.6dev/zh/others/change-log -->

# 版本迁移

AgentScope 2.0 是一次破坏性更新。下面按模块汇总相对 1.0 的差异。

## 智能体

- 重构 ReActAgent Agent
- 用 reply_stream reply __call__
- 支持从 reply_stream
- 通过事件流支持 权限校验 human-in-the-loop
- 通过新的 Offloader
- 废弃 hook 机制，由新的智能体中间件系统取代。
- 废弃 state_dict load_state_dict AgentState
- 废弃智能体类的 print
- 废弃智能体类内部的 OpenTelemetry 集成，交由新的中间件实现承担。

## Event New

- 新增 event 系统，更好地服务前端集成与 human-in-the-loop 场景。

## Message

Content block 重构：

- 重构所有 content block，统一继承自 Pydantic BaseModel
- 将 ImageBlock AudioBlock VideoBlock DataBlock media_type
- 新增 HintBlock
- 将 ToolUseBlock ToolCallBlock
- 为 ToolCallBlock state suggested_rules
- 为 ToolResultBlock state
- 为所有 block 新增 id

`Msg` 类重构：

- 重构 Msg BaseModel
- 为 Msg created_at finished_at usage
- 为 Msg append_event
- 新增 UserMsg AssistantMsg SystemMsg
- 为 content role

## Permission New

- 新增权限系统，用于工具执行的细粒度门控、human-in-the-loop 确认以及智能体整体自治度控制。

## 工具

- 新增 ToolBase
- 重构内置工具：
  - 新增 Bash Edit Glob Grep Read Write
  - 新增 TaskCreate TaskGet TaskList TaskUpdate

`Toolkit` 重构：

- 在 Toolkit
- 新增 ToolGroup basic
- 新增 ResetTools
- 新增 MCPTool FunctionTool

## MCP

- 将 MCP 实现重构为单一的 MCPClient
- 新增 StdioMCPConfig HttpMCPConfig

## Skill New

- 新增 skill loader 抽象，支持从文件系统 / sandbox / web 即时加载 skill。
- 新增 LocalSkillLoader
- 支持将 skill 打包为 ToolGroup

## Workspace New

- 新增 workspace 抽象，通过统一接口提供工具、MCP、skill 与上下文 offload 能力。
- 新增 LocalWorkspace DockerWorkspace E2BWorkspace
- 新增 Offloader Agent
- 新增 LocalWorkspaceManager DockerWorkspaceManager E2BWorkspaceManager 智能体级隔离
- 新增 in-workspace MCP gateway

## Model

- 将 credential 管理从 model 类中解耦，集中到新的 Credential
- 支持基于 credential 的模型列举与获取。
- 支持 Kimi、Moonshot、DeepSeek、XAI 与 OpenAI Response API。
- 将 formatter 集成到 chat model 抽象中，并为不同 model provider 提供默认 formatter。
- 新增 ModelCard
- 新增类方法 list_models
- 废弃 Trinity

## Middleware New

- 将 hook 机制重构为更通用的智能体中间件系统。
- 新增 TracingMiddleware

## Agent Service New

- 在 app
- 新增 create_app
- 新增 lifespan 周期内的 SessionManager SchedulerManager BackgroundTaskManager
- 新增 AGUIProtocolMiddleware ToolOffloadMiddleware
- 新增基于 Redis 的存储后端。

## Memory

- 在 2.0 中废弃 memory 模块，原因是该模块与智能体逻辑耦合过深。

## RAG & Long-Term Memory

- 将 RAG 与 long-term memory 统一到单一模块下。
- 从 1.0 到 2.0 的迁移正在进行中，knowledge base、document reader 与 store 将基于 2.0 架构在后续版本中陆续上线。

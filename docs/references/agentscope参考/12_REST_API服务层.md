# 12. REST API 服务层参考索引

> 面向 GerClaw 老年医疗 AI 平台开发者，基于 AgentScope 2.0.3 源码整理。
> 覆盖 `create_app` 工厂、全部 REST 端点、SSE 流式协议、认证机制、错误码规范，以及 GerClaw 医疗场景适配要点。

---

## 1. 模块映射总览

AgentScope 2.0.3 内置基于 FastAPI 的 Agent Service，通过 `agentscope.app.create_app` 工厂函数构建可嵌入或独立运行的 HTTP 服务。服务层采用经典的分层架构：

```
┌──────────────────────────────────────────────────────────┐
│                   FastAPI App (create_app)                │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Routers (9 个 APIRouter)                           │  │
│  │  /agent  /chat  /sessions  /credential  /model      │  │
│  │  /knowledge_bases  /schedule  /workspace  /tts-model│  │
│  └───────────────┬────────────────────────────────────┘  │
│                  │ Depends() 依赖注入                      │
│  ┌───────────────▼────────────────────────────────────┐  │
│  │  Services (业务逻辑层)                               │  │
│  │  ChatService / SessionService / KnowledgeBaseService│  │
│  │  SchedulerManager / BackgroundTaskManager           │  │
│  └───────────────┬────────────────────────────────────┘  │
│                  │                                        │
│  ┌───────────────▼────────────────────────────────────┐  │
│  │  Infrastructure (基础设施层)                         │  │
│  │  StorageBase (Redis)  MessageBus (Redis/InMemory)   │  │
│  │  WorkspaceManager  KBManager  BlobStore             │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**核心设计理念**：
- **多租户原生**：所有资源（Agent/Session/Credential/Schedule/KB）归属 `user_id`，通过请求头解析
- **Fire-and-Forget Chat**：`POST /chat` 仅触发后台任务立即返回，事件通过 SSE 长连接异步推送
- **会话即状态**：Agent 是可复用模板，Session 承载运行时状态；每个 `(user_id, agent_id, workspace_id)` 三元组最多一个 Session
- **消息总线解耦**：Redis MessageBus 是事件投递唯一通道，支持跨进程唤醒、取消、回放
- **可扩展工厂**：`create_app` 接收可插拔组件（存储、消息总线、工作区、知识库），支持 `extra_middlewares` / `extra_agent_middlewares` / `extra_agent_tools` 注入

**最简启动代码**：
```python
import uvicorn
from agentscope.app import create_app
from agentscope.app.storage import RedisStorage
from agentscope.app.message_bus import RedisMessageBus
from agentscope.app.workspace_manager import LocalWorkspaceManager

app = create_app(
    storage=RedisStorage(host="localhost", port=6379),
    message_bus=RedisMessageBus(host="localhost", port=6379),
    workspace_manager=LocalWorkspaceManager(basedir="/data/workspaces"),
)
uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 2. 核心 API 参考

### 2.1 `create_app` 完整参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `storage` | `StorageBase` | **必填** | 持久化后端（Agent/Session/Credential/Message/Schedule），生命周期由 lifespan 管理 |
| `message_bus` | `MessageBus` | **必填** | 消息总线（会话锁、回放日志、收件箱、唤醒信号），与 storage 解耦可使用不同后端 |
| `workspace_manager` | `WorkspaceManagerBase` | **必填** | 工作区管理器（Local/Docker/E2B），每个 chat run 和 `/workspace` 端点依赖 |
| `knowledge_base_manager` | `KnowledgeBaseManagerBase \| None` | `None` | RAG 知识库管理器，`None` 时禁用全部 KB 端点（返回 503） |
| `knowledge_parsers` | `list[ParserBase] \| dict \| None` | `[TextParser()]` | 文档解析器列表；list 按 `supported_media_types` 路由，dict 显式映射 |
| `knowledge_chunker` | `ChunkerBase \| None` | `ApproxTokenChunker()` | 所有 KB 共享的切块策略 |
| `blob_store` | `BlobStoreBase \| None` | `LocalBlobStore('./blobs')` | 上传文件二进制存储（Local/S3） |
| `enable_index_worker` | `bool` | `True` | API 进程内是否嵌入索引 worker；`False` 时需独立 worker 进程 |
| `extra_credentials` | `list[Type[CredentialBase]] \| None` | `None` | 额外注册的凭证类型 |
| `extra_middlewares` | `list[Middleware] \| None` | `None` | 额外 ASGI 中间件（CORS、JWT、协议适配等） |
| `extra_agent_middlewares` | `AgentMiddlewareFactory \| None` | `None` | 异步工厂 `(user_id, agent_id, session_id) -> list[MiddlewareBase]`，每次组装 Agent 时调用，可注入租户隔离/审计/鉴权中间件 |
| `extra_agent_tools` | `AgentToolFactory \| None` | `None` | 异步工厂 `(user_id, agent_id, session_id) -> list[ToolBase]`，每次组装 Agent 时注入动态工具 |
| `custom_subagent_templates` | `list[SubAgentTemplate] \| None` | `None` | 团队子智能体可复用蓝图，注册后 `AgentCreate` 工具暴露 `subagent_type` 参数 |
| `custom_agent_cls` | `Type[Agent] \| None` | `None` | 自定义 Agent 子类，默认使用内置 `Agent` |
| `title` | `str` | `"AgentScope"` | OpenAPI 文档标题 |
| `version` | `str` | 包版本号 | API 版本号 |

### 2.2 认证方式

**当前版本（2.0.3）使用 Header 占位鉴权**：
- 所有端点要求 `X-User-ID` 请求头，缺失或空返回 `401 Unauthorized`
- 源码注释明确标注："Temporary header-based identity; will be replaced by JWT auth."
- 通过 FastAPI 依赖覆盖机制替换为自定义鉴权：

```python
from fastapi import FastAPI, Header, HTTPException, status

async def jwt_auth(authorization: str = Header(...)) -> str:
    """JWT Bearer Token 鉴权示例（GerClaw 生产环境使用）"""
    token = authorization.removeprefix("Bearer ")
    payload = verify_jwt(token)  # 自行实现 JWT 验证
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token")
    return payload["sub"]  # 返回 user_id

app = create_app(storage=..., message_bus=..., workspace_manager=...)
app.dependency_overrides[get_current_user_id] = jwt_auth
```

### 2.3 所有 REST 端点列表及用途

#### 2.3.1 Chat（聊天触发）

| 方法 | 路径 | 用途 |
|------|------|------|
| `POST` | `/chat/` | 触发会话的一次 chat run（fire-and-forget），后台启动任务，立即返回 `{status: "started", session_id}` |

**请求体 `ChatRequest`**：
```json
{
  "agent_id": "string (必填)",
  "session_id": "string (必填)",
  "input": "Msg | list[Msg] | UserConfirmResultEvent | ExternalExecutionResultEvent | null"
}
```

`input` 三种 payload：
- `Msg` / `list[Msg]`：新用户消息，直接 spawn 到 ChatRunRegistry
- `UserConfirmResultEvent` / `ExternalExecutionResultEvent`：HITL 恢复，经 WakeupDispatcher 串行化
- `null`：从当前状态继续执行

**错误码**：
- `409 Conflict`：同 session 已有 run 在执行（double-submit guard）
- `401 Unauthorized`：缺少 X-User-ID

#### 2.3.2 Session 流式事件（SSE）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/sessions/{session_id}/stream` | 订阅会话 SSE 事件流（核心实时通道） |

**参数**：
- Path: `session_id`
- Query: `agent_id`（必填，所有权校验）
- Header: `X-User-ID`（必填）

**SSE 协议规范**：
- Content-Type: `text/event-stream`
- Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`
- 帧格式：`data: {JSON}\n\n`（标准 SSE data 帧）
- 心跳帧：每 30 秒发送注释帧 `:\n\n` 保持连接
- 连接语义：先重放缓冲事件（`SESSION_REPLAY_MAX_LEN` 条），再实时推送；同一连接可接收多次 chat 触发的事件；支持多订阅者扇出
- 断线重连：后接入客户端自动收到缓冲历史回放

#### 2.3.3 Sessions（会话管理）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/sessions/` | 列出某 agent 的所有会话（Query: `agent_id`），返回含运行状态和团队详情 |
| `POST` | `/sessions/` | 创建（或恢复）会话；同 `(user_id, agent_id, workspace_id)` 三元组幂等 |
| `PATCH` | `/sessions/{session_id}` | 更新会话配置（模型、权限模式等，Query: `agent_id`） |
| `DELETE` | `/sessions/{session_id}` | 删除会话（级联取消 in-flight run、清除消息和 bus 状态） |
| `GET` | `/sessions/{session_id}/messages` | 分页获取历史消息（Query: `agent_id`, `offset`, `limit`，1-200） |

**创建会话请求体**：
```json
{
  "agent_id": "string (必填)",
  "workspace_id": "string | null (null时自动生成)",
  "name": "string | null",
  "chat_model_config": {
    "type": "string (必填，如 'dashscope_chat')",
    "credential_id": "string (必填)",
    "model": "string (必填，如 'qwen-plus')",
    "parameters": {}
  },
  "fallback_chat_model_config": "ChatModelConfig | null",
  "tts_model_config": "TTSModelConfig | null",
  "knowledge_config": {"knowledge_base_ids": ["kb-id-1"]}
}
```

#### 2.3.4 Agents（智能体管理）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/agent/schema` | 获取 Agent 创建/编辑表单的 JSON Schema（identity/context_config/react_config 三段） |
| `GET` | `/agent/` | 列出当前用户的所有 Agent |
| `POST` | `/agent/` | 创建新 Agent（201 Created） |
| `PATCH` | `/agent/{agent_id}` | 部分更新 Agent 配置 |
| `DELETE` | `/agent/{agent_id}` | 删除 Agent（级联删除所有 Session、Schedule） |

**创建 Agent 请求体**：
```json
{
  "name": "string (必填，展示名)",
  "system_prompt": "string (默认 'You are a helpful assistant.')",
  "context_config": {
    "trigger_ratio": 0.8, "reserve_ratio": 0.1,
    "compression_prompt": "...", "tool_result_limit": 3000
  },
  "react_config": {"max_iters": 20, "stop_on_reject": false}
}
```

#### 2.3.5 Credentials（凭证管理）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/credential/schemas` | 列出所有注册凭证类型的 JSON Schema（动态表单渲染） |
| `GET` | `/credential/` | 列出当前用户的所有凭证 |
| `POST` | `/credential/` | 存储新凭证（API Key 等，201 Created） |
| `PATCH` | `/credential/{credential_id}` | 更新凭证 payload |
| `DELETE` | `/credential/{credential_id}` | 删除凭证 |

#### 2.3.6 Models（模型发现）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/model/` | 列出指定 provider 下的候选对话模型（Query: `provider=<type>`，如 `dashscope_chat`） |
| `GET` | `/tts-model/` | 列出指定 provider 下的候选 TTS 模型（Query: `provider=<type>`） |

#### 2.3.7 Knowledge Bases（知识库管理，需启用 KB manager）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/knowledge_bases/embedding_models` | 列出与向量库维度兼容的嵌入模型 |
| `GET` | `/knowledge_bases/middleware/parameters_schema` | RAGMiddleware 参数 JSON Schema |
| `GET` | `/knowledge_bases/supported_content_types` | 已挂载解析器支持的文件类型 |
| `POST` | `/knowledge_bases/` | 创建知识库（201 Created） |
| `GET` | `/knowledge_bases/` | 列出当前用户的知识库 |
| `PATCH` | `/knowledge_bases/{kb_id}` | 更新知识库（仅 name/description 可变） |
| `DELETE` | `/knowledge_bases/{kb_id}` | 删除知识库（级联清理 vector collection 和文档） |
| `GET` | `/knowledge_bases/{kb_id}/documents` | 列出知识库中的文档（含 pending/parsing/error/ready 状态） |
| `POST` | `/knowledge_bases/{kb_id}/documents` | 上传文档（multipart/form-data，异步索引） |
| `DELETE` | `/knowledge_bases/{kb_id}/documents/{doc_id}` | 删除文档及其 chunks |
| `GET` | `/knowledge_bases/{kb_id}/documents/status` | 批量查询文档索引状态（Query: `ids=a,b,c`） |
| `POST` | `/knowledge_bases/{kb_id}/search` | 自然语言检索，返回 top-K 相似 chunks |

#### 2.3.8 Schedules（定时任务）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/schedule/` | 列出当前用户的所有定时任务 |
| `POST` | `/schedule/` | 创建 cron 定时任务（201 Created） |
| `PATCH` | `/schedule/{schedule_id}` | 更新定时任务（变更 cron/timezone 立即重新调度） |
| `DELETE` | `/schedule/{schedule_id}` | 删除定时任务（级联取消触发的 sessions） |
| `GET` | `/schedule/{schedule_id}/sessions` | 列出该定时任务触发的执行会话历史 |

**创建 Schedule 请求体**：
```json
{
  "name": "string",
  "description": "string",
  "agent_id": "string (必填)",
  "cron_expression": "string (必填，标准5段cron)",
  "timezone": "string (默认 'UTC')",
  "enabled": true,
  "stateful": false,
  "permission_mode": "accept_always | confirm_before_execute | ...",
  "chat_model_config": { ... }
}
```

#### 2.3.9 Workspace（工作区 MCP/Skill 管理）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/workspace/mcp` | 列出会话 workspace 的 MCP clients（含工具列表和健康状态） |
| `POST` | `/workspace/mcp` | 添加 MCP client（Query: `agent_id`, `session_id`） |
| `DELETE` | `/workspace/mcp/{mcp_name}` | 移除 MCP client |
| `GET` | `/workspace/skill` | 列出可用 skills |
| `POST` | `/workspace/skill` | 从路径添加 skill |
| `DELETE` | `/workspace/skill/{skill_name}` | 移除 skill |

### 2.4 SSE 流式协议详解

Agent Service 采用 **fire-and-forget + SSE 订阅** 的双连接模式：

```
客户端                         Agent Service
  │                                │
  │─── POST /chat (input=Msg) ───→│ 立即返回 {status:"started"}
  │                                │ 后台 spawn ChatService.run()
  │                                │
  │←── 200 {status:"started"} ─────│
  │                                │
  │─── GET /sessions/{sid}/stream →│ (text/event-stream 长连接)
  │                                │ 1. 先重放缓冲事件
  │← data: {event1} ──────────────│
  │← data: {event2} ──────────────│ 2. 实时推送 AgentEvent
  │← data: {event3} ──────────────│
  │← : (heartbeat every 30s) ────│ 3. 心跳保活
  │← data: {eventN} ──────────────│
  │        ...                     │
```

**事件类型（`AgentEvent` 子类）**：
- `MsgEvent`：包含 Msg 对象（user/assistant/system 的 TextBlock/ToolCallBlock/ToolResultBlock 等）
- `CustomEvent`：自定义事件（如 SubagentHitlProjector 的 `require_confirm` 事件）
- 其他内部事件（状态变更、工具执行等）

**核心消息结构 `Msg`**：
```json
{
  "name": "string",
  "role": "user | assistant | system",
  "content": [
    {"type": "text", "text": "string", "id": "string"},
    {"type": "thinking", "thinking": "string", "id": "string"},
    {"type": "tool_call", "id": "string", "name": "string",
     "input": "string", "state": "pending|asking|allowed|submitted|finished"},
    {"type": "tool_result", "id": "string", "name": "string",
     "output": "...", "state": "success|error|interrupted|denied|running"}
  ],
  "id": "string",
  "usage": {"input_tokens": 0, "output_tokens": 0}
}
```

### 2.5 错误码规范

| HTTP 状态码 | 含义 | 触发场景 |
|-------------|------|---------|
| `400 Bad Request` | 请求参数错误 | Pydantic 校验失败、字段缺失/格式错误 |
| `401 Unauthorized` | 未认证 | `X-User-ID` 头缺失或为空（自定义 JWT 鉴权时 token 无效） |
| `404 Not Found` | 资源不存在 | Agent/Session/Credential/KB/Schedule 不存在或不属于当前用户 |
| `409 Conflict` | 冲突 | 同一 session 已有 chat run 在执行（double-submit） |
| `503 Service Unavailable` | 功能未启用 | KB 相关端点在 `knowledge_base_manager=None` 时调用 |
| `201 Created` | 创建成功 | POST 创建 Agent/Credential/Session/KB/Schedule/Document |
| `204 No Content` | 删除成功 | DELETE 操作无返回体 |

---

## 3. 源码路径索引

基于 `/references/agentscope/src/agentscope/app/` 目录：

### 3.1 应用入口与生命周期

| 文件 | 职责 |
|------|------|
| `_app.py` | `create_app()` 工厂函数，FastAPI 实例创建、router 注册、middleware 挂载 |
| `_lifespan.py` | `lifespan` 异步上下文管理器，统一管理 storage/message_bus/workspace/kb/blob_store 的启动/关闭顺序 |
| `deps.py` | FastAPI 依赖注入函数（`get_current_user_id`, `get_storage`, `get_chat_service` 等 13 个依赖） |
| `__init__.py` | 导出 `create_app` 和 `SubAgentTemplate` |
| `_types.py` | `AgentMiddlewareFactory`, `AgentToolFactory`, `SubAgentTemplate` 类型定义 |
| `_bus_ops.py` | 消息总线操作辅助函数（`enqueue_run_trigger` 等） |

### 3.2 路由层 `_router/`

| 文件 | Prefix | 端点数 |
|------|--------|--------|
| `_router/_chat.py` | `/chat` | 1 |
| `_router/_session.py` | `/sessions` | 6（含 SSE stream） |
| `_router/_agent.py` | `/agent` | 5 |
| `_router/_credential.py` | `/credential` | 5 |
| `_router/_knowledge_base.py` | `/knowledge_bases` | 13 |
| `_router/_model.py` | `/model` | 1 |
| `_router/_tts_model.py` | `/tts-model` | 1 |
| `_router/_schedule.py` | `/schedule` | 5 |
| `_router/_workspace.py` | `/workspace` | 6（MCP 3 + Skill 3） |
| `_router/_schema/` | — | Pydantic 请求/响应模型（每个 router 对应一个 schema 文件） |

### 3.3 服务层 `_service/`

| 文件 | 职责 |
|------|------|
| `_service/_chat.py` | `ChatService`：核心聊天运行时，Agent 组装、ReAct 循环、事件发布 |
| `_service/_session.py` | `SessionService`：会话删除（级联清理）、Agent 删除 |
| `_service/_knowledge_base.py` | `KnowledgeBaseService`：KB CRUD、文档上传/检索、索引任务发布 |
| `_service/_model.py` | 模型配置服务 |
| `_service/_tts_model.py` | TTS 模型服务 |
| `_service/_embedding.py` | 嵌入服务 |
| `_service/_index_worker.py` | `IndexWorker`：文档解析/切块/嵌入/写入向量库 |
| `_service/_index_task_consumer.py` | `IndexTaskConsumer`：从 message_bus 消费索引任务 |
| `_service/_index_sweeper.py` | `IndexSweeper`：周期扫描未完成任务重新入队（容灾自愈） |
| `_service/_session_projection.py` | `SessionProjection`：跨会话事件投影（HITL 卡片投影到 leader） |
| `_service/_projectors/_subagent_hitl.py` | `SubagentHitlProjector`：子 Agent HITL 确认投影到 leader |
| `_service/_toolkit.py` | Agent 工具集组装（workspace 工具 + extra_agent_tools） |

### 3.4 管理器层 `_manager/`

| 文件 | 职责 |
|------|------|
| `_manager/_chat_run_registry.py` | `ChatRunRegistry`：单 session 单 run 保证，in-flight 任务追踪 |
| `_manager/_background_task_manager.py` | `BackgroundTaskManager`：工具执行卸载（长任务切后台） |
| `_manager/_scheduler_manager.py` | `SchedulerManager`：APScheduler cron 调度封装 |
| `_manager/_cancel_dispatcher.py` | `CancelDispatcher`：跨进程取消广播 |
| `_manager/_wakeup_dispatcher.py` | `WakeupDispatcher`：唤醒信号消费，串行化 spawn（解决 409 竞态） |
| `_manager/_scheduler/` | 调度工具实现（`_schedule_create.py` 等） |

### 3.5 基础设施层

| 目录 | 职责 |
|------|------|
| `storage/` | `StorageBase` 抽象 + `RedisStorage` 实现 + 数据模型（AgentRecord/SessionRecord 等） |
| `message_bus/` | `MessageBus` 抽象 + `InMemoryMessageBus` / `RedisMessageBus` 实现 |
| `workspace_manager/` | `WorkspaceManagerBase` + Local/Docker/E2B 三种实现 |
| `rag/` | RAG 完整管线：blob_store/、knowledge_base_manager/、index_worker/ |
| `middleware/` | Agent 级中间件（InboxMiddleware、ToolOffloadMiddleware、StateChangeMiddleware、协议适配） |
| `message_bus/_keys.py` | 消息总线 channel key 生成（session_events、session_lock、inbox 等） |

---

## 4. 官方示例参考

### 4.1 内置示例目录

| 示例路径 | 说明 |
|---------|------|
| `examples/agent_service/main.py` | 最简 Agent Service 启动（Redis 存储+消息总线+LocalWorkspace） |
| `examples/web_ui/` | 配套 React 前端（pnpm dev 启动），展示完整的 API 调用流程 |

### 4.2 典型操作流程（5 步）

1. **创建凭证**：`GET /credential/schemas` → `POST /credential`（提交 API Key）
2. **创建 Agent**：`POST /agent`（定义 system prompt、运行参数）
3. **创建 Session**：`POST /sessions`（绑定 agent + model config + workspace）
4. **（可选）配置 Workspace**：`POST /workspace/mcp`、`POST /workspace/skill`
5. **开始对话**：
   - 建立 SSE 连接：`GET /sessions/{sid}/stream?agent_id={aid}`
   - 发送消息：`POST /chat` `{"agent_id":..., "session_id":..., "input": Msg}`
   - 从 SSE 流中实时接收事件

### 4.3 测试文件参考

`references/agentscope/tests/` 下的 `service_*.py` 文件可作为 API 调用的参考实现：

| 测试文件 | 参考价值 |
|---------|---------|
| `service_message_bus_test.py` | MessageBus API 使用模式 |
| `service_scheduler_test.py` | Schedule 创建/更新/删除流程 |
| `service_wakeup_dispatcher_test.py` | 唤醒分发机制 |
| `service_cancel_dispatcher_test.py` | 取消机制 |
| `service_knowledge_base_upload_test.py` | KB 文档上传和索引流程 |
| `service_team_tools_test.py` | Agent Team 多智能体协作 |
| `service_subagent_hitl_projector_test.py` | HITL 确认投影机制 |

---

## 5. 文档链接

| 文档 | 位置 | 说明 |
|------|------|------|
| Agent Service 架构 | `agentscope文档离线/group_B9-11_C_D.md` 第 4 章 | 概述、快速上手、create_app 参数、操作流程、资源模型、自定义扩展 |
| RAG 服务 | `agentscope文档离线/group_B9-11_C_D.md` 第 6 章 | KB 配置、部署形态（单进程/分布式）、create_app RAG 参数、REST API |
| API 概览 | `agentscope文档离线/group_B9-11_C_D.md` 第 7 章 | 38+ 端点分类清单、Msg 数据结构、通用约定 |
| Agent Team | `agentscope文档离线/group_B9-11_C_D.md` 第 5 章 | 团队概念、SubAgentTemplate、内置工具、分布式协调 |
| 源码映射 | `agentscope文档离线/source_map_advanced.md` 第 3 章 | 完整文件树、create_app 签名、REST 路由清单、依赖注入表 |
| OpenAPI 文档 | 运行服务后访问 `http://localhost:8000/docs` | Swagger UI 交互式 API 文档 |
| 离线文档首页 | `references/agentscope/README.md` / `README_zh.md` | 项目总览和快速开始 |

---

## 6. GerClaw 适配要点

### 6.1 医疗 API 安全：JWT 认证 + 患者数据权限

**问题**：AgentScope 内置 `get_current_user_id` 仅读取 `X-User-ID` 头，无真正认证，注释标记为临时方案。医疗场景必须强化。

**实施方案**：

1. **替换认证依赖**（强制 JWT）：
```python
from jose import JWTError, jwt
from fastapi import Header, HTTPException, status, Depends

JWT_SECRET = os.environ["GERCLAW_JWT_SECRET"]
JWT_ALGORITHM = "HS256"

async def gerclaw_auth(authorization: str = Header(...)) -> str:
    """GerClaw JWT 认证：验证 token 并返回 user_id（医生/患者ID）"""
    try:
        token = authorization.removeprefix("Bearer ")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        role: str = payload.get("role", "patient")  # doctor/patient/admin
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        # 将角色存入 request.state 供后续授权使用
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

app = create_app(storage=..., message_bus=..., workspace_manager=...)
app.dependency_overrides[get_current_user_id] = gerclaw_auth
```

2. **患者数据权限隔离**（通过 `extra_agent_middlewares` 注入）：
```python
async def medical_audit_middleware(user_id, agent_id, session_id):
    """每次 Agent 组装时注入医疗审计+权限中间件"""
    return [
        PatientDataAccessMiddleware(user_id=user_id),  # 患者数据行级权限
        AuditLogMiddleware(user_id=user_id),           # 医疗操作审计日志
        DesensitizationMiddleware(),                   # 响应数据脱敏
    ]

app = create_app(
    ...,
    extra_agent_middlewares=medical_audit_middleware,
)
```

3. **CORS 和安全头**：
```python
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware import Middleware
from agentscope.app import create_app

app = create_app(
    ...,
    extra_middlewares=[
        Middleware(CORSMiddleware,
                   allow_origins=["https://gerclaw.example.com"],
                   allow_credentials=True,
                   allow_methods=["*"],
                   allow_headers=["*"]),
        Middleware(SecurityHeadersMiddleware),  # HSTS, X-Frame-Options 等
    ],
)
```

### 6.2 推荐配置：create_app + Redis 持久化 + 多租户

GerClaw 生产环境推荐配置：

```python
import os
import uvicorn
from agentscope.app import create_app, SubAgentTemplate
from agentscope.app.storage import RedisStorage
from agentscope.app.message_bus import RedisMessageBus
from agentscope.app.workspace_manager import LocalWorkspaceManager
from agentscope.app.rag.knowledge_base_manager import CollectionPerKbManager
from agentscope.app.rag.blob_store import S3BlobStore
from agentscope.rag import QdrantStore, TextParser, PDFParser, ApproxTokenChunker

REDIS_URL = os.environ["REDIS_URL"]
S3_BUCKET = os.environ.get("GERCLAW_S3_BUCKET", "gerclaw-blobs")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")

storage = RedisStorage(url=REDIS_URL)
message_bus = RedisMessageBus(url=REDIS_URL)
workspace_manager = LocalWorkspaceManager(
    basedir="/data/gerclaw/workspaces",
    ttl=86400.0,  # 24 小时 TTL，老年用户会话长
)

# 医疗知识库（老年慢病指南、药品说明书等）
vector_store = QdrantStore(url=QDRANT_URL)
kb_manager = CollectionPerKbManager(storage=storage, vector_store=vector_store)

app = create_app(
    storage=storage,
    message_bus=message_bus,
    workspace_manager=workspace_manager,
    # RAG 配置
    knowledge_base_manager=kb_manager,
    knowledge_parsers=[TextParser(), PDFParser()],
    knowledge_chunker=ApproxTokenChunker(chunk_size=512, overlap=50),
    blob_store=S3BlobStore(bucket=S3_BUCKET),
    enable_index_worker=True,  # 初期单进程部署，量大后拆分为分布式
    # 医疗子 Agent 模板
    custom_subagent_templates=[
        SubAgentTemplate(type="cga_assessor", ...),  # CGA评估
        SubAgentTemplate(type="medication_reviewer", ...),  # 用药审查
        SubAgentTemplate(type="care_advisor", ...),  # 护理顾问
    ],
    title="GerClaw Medical AI",
    version="1.0.0",
)
```

**多租户策略**：
- 天然多租户：所有资源按 `user_id`（医生/患者 ID）隔离
- Redis key 命名空间：AgentScope 内部已按 user_id 分区
- 医疗知识库：可按 `tenant_id` 或科室维度在 KB 层面做隔离
- 建议在 `extra_agent_middlewares` 中验证用户对特定 session/agent 的访问权限

### 6.3 风险：SSE 连接断开 / 长任务超时

**风险 1：SSE 连接断开**
- **现象**：老年用户网络不稳定、移动端切后台、反向代理超时导致 SSE 断连
- **影响**：消息丢失、前端无响应、用户重复发送
- **应对**：
  - 客户端自动重连（EventSource 默认支持），服务端自动重放缓冲事件（已内置）
  - 反向代理配置：Nginx 设置 `proxy_read_timeout 3600s`，添加 `X-Accel-Buffering: no`（已内置）
  - 前端检测连接状态，断连时显示"正在重连"提示（适老化 UI）
  - 心跳间隔 30s 已内置，确保 NAT/负载均衡器不切断空闲连接

**风险 2：长任务超时**
- **现象**：CGA 评估、多轮 RAG 检索、用药审查等长任务可能超过 60s
- **影响**：Agent run 被中断、工具执行无结果、用户困惑
- **应对**：
  - 使用 `BackgroundTaskManager`（已内置）：长耗时工具调用切到后台执行，完成时通过事件流回送结果
  - uvicorn 配置 `timeout_keep_alive=300`（但不建议设太大）
  - 前端显示进度：订阅 SSE 流中的 `tool_call` 状态事件（`pending→submitted→finished`），向老年用户展示"正在分析您的用药数据..."
  - Cron 定时任务（`/schedule`）用于非实时任务，如每日健康报告生成

**风险 3：单 session 并发冲突（409）**
- **现象**：用户快速重复发送消息，触发 409 Conflict
- **应对**：前端应在 chat run 进行中禁用发送按钮；或客户端排队串行发送
- 源码 `ChatRunRegistry` 强制单 session 单 run，是有意的 double-submit 防护

**风险 4：Redis 不可用**
- **现象**：Redis 故障导致所有会话状态丢失
- **应对**：生产环境 Redis 哨兵/集群模式；lifespan 启动时会进入 storage context，连接失败直接启动失败（fail-fast）

---

## 7. 可运行示例指引

### 7.1 示例文件清单

| 示例文件 | 路径 | 说明 |
|---------|------|------|
| HTTP 客户端示例 | `agentscope-examples/12_rest_api/rest_api_client.py` | 演示用 httpx 调用 `/health`（自定义）、`/api/chat`、SSE 流式解析，含认证 header、mock server 模式 |
| GerClaw 医疗 API 服务 | `agentscope-examples/12_rest_api/gerclaw_api_server.py` | 演示 `create_app` + 自定义医疗路由（`/api/medical/consult` 问诊、`/api/medical/cga` 评估），JWT 认证、医疗业务逻辑包装 |

### 7.2 运行前准备

```bash
# 安装依赖
pip install agentscope fastapi uvicorn httpx pydantic python-multipart

# 启动 Redis（Agent Service 必需）
# Docker 方式：
docker run -d -p 6379:6379 redis:7-alpine

# 设置 DashScope API Key（通义千问）
export DASHSCOPE_API_KEY="sk-your-key-here"
```

### 7.3 运行示例

```bash
# 终端 1：启动 GerClaw API 服务
cd agentscope-examples/12_rest_api
python gerclaw_api_server.py
# 服务在 http://localhost:8000 启动
# OpenAPI 文档: http://localhost:8000/docs

# 终端 2：运行 HTTP 客户端示例
cd agentscope-examples/12_rest_api
python rest_api_client.py
# 演示：健康检查 → 创建 Agent → 创建 Session → 发送消息 → SSE 流式接收
```

### 7.4 调用流程示例

```
1. POST /api/medical/consult          # GerClaw 自定义问诊端点
2.   内部调用 AgentScope ChatService   # 复用底层 Agent
3.   包装医疗业务逻辑（患者校验、记录审计）
4. GET /sessions/{sid}/stream          # SSE 订阅实时响应
5.   data: {MsgEvent}                  # 流式返回 AI 回复
6.   data: {tool_call state=finished}  # 工具调用完成事件
```

### 7.5 扩展方向

- 在 `gerclaw_api_server.py` 基础上添加更多医疗端点：用药审查（`/api/medical/drug-review`）、健康画像（`/api/medical/profile`）、随访问卷（`/api/medical/followup`）
- 通过 `extra_agent_tools` 注入 GerClaw 专用工具：HIS 系统查询、EMR 读取、检验报告解读
- 通过 `custom_subagent_templates` 预定义老年科医生、药师、营养师、护理师等角色模板
- 集成微信小程序：小程序端通过 WebSocket ↔ 服务端 SSE 桥接接入

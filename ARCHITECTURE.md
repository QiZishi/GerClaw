# GerClaw 架构

> 本文描述仓库的**当前真实架构**和强制边界；设计目标以 [gerclaw设计要求.md](docs/references/gerclaw设计要求.md) 为最高权威，逐项完成度以 [需求→模块→验收矩阵](docs/REQUIREMENTS_MATRIX.md) 为准。本文不把计划、静态 UI 或未审核临床规则表述为已交付能力。

## 1. 系统目标

GerClaw 是面向老年患者与老年科医生的 Web 端 AI 辅助诊疗与康养系统。它以语音优先、适老化交互、透明执行过程、医疗安全与可追溯证据为目标；系统不作确定性诊断，不把未审核临床规则或前端界面当作可执行医疗服务。

## 2. 当前部署单元与边界

`apps/mvp` 是当前唯一功能性 Web 客户端（Next.js 16 + React 19），同时承载浏览器可访问页面和 server-only BFF 路由；`apps/web` 是刻意保留的空目录，不是运行入口，也不应复制出第二套前端。`apps/api` 是 FastAPI + AgentScope 2.0.4 服务，使用 PostgreSQL、Redis 与 Qdrant。根目录 `app.py` 是开发启动入口。

```text
患者 / 医生浏览器
  │  HTTPS；只发送浏览器安全的请求体
  ▼
apps/mvp (Next.js 页面 + BFF)
  │  server-only 短期访客 JWT；Zod 校验
  ▼
apps/api (FastAPI)
  ├─ 认证、限流、Pydantic 校验与统一错误边界
  ├─ Runtime / Agent Harness 与安全后处理
  ├─ 业务模块（Chat、RAG、Memory、Skill、Search、CGA、资料登记、临床信息收集）
  ├─ PostgreSQL（加密事实源）与 Redis（租约、限流、取消）
  └─ Qdrant（公开医学语料 / 无 PHI 的记忆引用向量）
       │
       ├─ 本地知识库（仅服务端摄取）
       └─ 经环境变量配置的 LLM、Search、ASR/TTS、MinerU、Embedding/Rerank Provider
```

浏览器不得直连模型、检索、数据库或 Provider。Provider key、数据库凭证、MinerU 上传凭证和 FastAPI JWT 均不得进入浏览器 bundle、localStorage、Trace 或日志。

## 3. 推荐技术栈

| 层级 | 当前技术 | 使用边界 |
|---|---|---|
| Web | Next.js 16、React 19、TypeScript、Tailwind、Zod | `apps/mvp` 是唯一功能前端与 BFF；外部 Provider 仅由 server-only route 调用 |
| API / Agent | FastAPI、Pydantic、AgentScope 2.0.4 | 认证、Runtime Harness、业务模块、SSE 与 Provider adapter |
| 持久化 | PostgreSQL、Redis、Qdrant | PostgreSQL 为加密事实源；Redis 处理租约/限流/取消；Qdrant 不存 PHI 正文 |
| 部署 | Docker Compose、Alembic、uv/npm | 基础编排可用于开发；最终应用 Docker 交付仍未完成 |

所有模型、外部 URL、密钥和协议均通过环境变量配置；实现选择应遵循“设计要求优先、AgentScope 能力优先、必要时才引入补充依赖”。

## 4. 已实现的运行链路

### 2.1 通用对话

`POST /api/v1/chat` 经过 BFF 访客身份、FastAPI scope/tenant/actor 校验、Redis 主体限流、PostgreSQL fencing token 和 Redis 会话 owner lease。服务端按 turn 隔离 AgentScope 状态，执行红旗症状短路、RAG/Memory/Skill/Search 的受限调用、模型 failover、医疗安全后处理和 PHI-free Trace。完成、失败与取消终态必须写入一致的数据库事务；SSE `done` 只会在提交后发送。

红旗症状在模型和 RAG 前使用确定性安全回应结束；这不是模型或临床诊断结论。普通聊天产生医疗内容时，需要可验证的本地证据与引用；证据不可用则 fail closed。

### 2.2 当前 Runtime Harness

`apps/api/src/gerclaw_api/modules/runtime/` 提供版本化 Capability、`RuntimePrincipal`、Pydantic Tool 输入边界、预算、PermissionEngine 与 AgentScope `GovernedTool` 代理。`modules/workflows` 还对当前实际可进入 Chat 的 `standard`、`cga` 与 `companion` workflow 执行版本、责任模块、允许上下文和 workflow 风险档案核验；该定义版本会写入受限 Trace 属性。生产 Chat Toolkit 在注册表之前还会经过 `security_evaluation` 的版本绑定风险档案门禁；执行顺序是：服务器拥有的风险档案/注册表 → schema/字节数校验 → AgentScope 与 Runtime 双重授权 → 超时/输出上限 → Trace/终态。

- 未注册工具、版本不匹配、缺 scope/角色、未验证患者访问、未脱敏的敏感外发与 critical action 默认拒绝。
- 高风险或副作用工具需要幂等键和持久化人工审批；当前临床副作用 resume executor 尚未投入业务流程。
- Runtime 预算限制步骤、重试、模型/工具调用、token、输出和 wall clock，不能由浏览器或模型扩大。

### 2.3 数据与信任边界

| 边界 | 当前强制控制 | 事实来源 / 未完成边界 |
|---|---|---|
| 身份与会话 | BFF 签名访客 cookie、短期 JWT、scope、tenant/actor 所有权、限流 | 当前只有访客身份；患者/医生账号、RBAC、患者授权未实现 |
| 对话与 Trace | Pydantic/Zod、会话 lease、加密消息、PHI-free Trace | 反馈/Bad Case 的完整授权晋升、回放治理尚未完成 |
| RAG | 本地 Markdown 白名单、内容净化、不可信证据隔离、Qdrant public payload | 当前知识库已真实进入 Chat；RAG 专项评测仍不完整 |
| Memory | PostgreSQL 加密事实与 revision 审计；Qdrant 仅无 PHI reference vector | 生命周期删除、受控再识别与完整分类注册表未实现 |
| 文档 | Next.js server-only MinerU BFF；FastAPI 加密会话资料登记与租户绑定 | 私有向量检索、病毒扫描、真实账号授权和 FastAPI Provider adapter 未完成 |
| 语音 | 受限 `/api/gerclaw/voice/*` BFF 唯一代理 FastAPI Voice Runtime；有请求大小/格式约束、24kHz PCM16 与浏览器 WAV 封装播放 | 真实人声的质量、取消和浏览器播放端到端评测，以及 adapter version 协商未完成 |
| CGA | PHQ-9、SAS、PSQI 的版本化状态机、确定性计分、加密持久化与报告导出 | Mini-Cog/MMSE 人工确认、医生授权和跨时间比较未完成 |
| 临床收集 | 五大处方/用药审查的加密、版本化最小信息收集与 MinerU 资料绑定 | 没有经医学审核的模板/规则/报告/审批；不能输出处方、药物调整或诊断结论 |

## 5. 分层依赖

```text
apps/mvp
  app / components
       ↓
  services（唯一业务 API client）
       ↓
  BFF routes（server-only 凭证与 Zod boundary）
       ↓
  FastAPI

apps/api
  api/routes → services → modules / repositories / providers
                         ↓
                 database + Redis + Qdrant + configured providers
```

- React 组件只能调用 `services/`，不得嵌入 Provider URL、业务结果或密钥。
- FastAPI 路由只负责 HTTP/SSE、认证、错误映射和依赖注入；业务逻辑在 `services/`，可替换能力在 `modules/`，存取在 `repositories/`。
- `modules/` 的对外契约使用严格 Pydantic model；前端 BFF 边界使用 Zod。未知字段、超限输入和不兼容版本应拒绝而非静默兼容。
- 每个核心模块的 `AGENTS.md` 约束依赖与测试；`README.md` 描述接口、配置和未完成边界。未实际接入的模块不得凭目录或文档宣称可用。

## 6. 数据边界

所有下列对象都按不可信输入处理，先做认证、版本/schema、大小与内容策略验证，再向下游传递：浏览器请求、上传文件、MinerU/ASR/TTS/LLM Provider 响应、检索片段、网页内容、工具输入输出和数据库回读。

| 数据流 | 允许的处理 | 禁止行为 |
|---|---|---|
| 浏览器 → BFF/API | Zod/Pydantic 验证、限流、所有权校验、可观察的稳定错误 | 浏览器自报角色、患者授权、预算或 Provider 凭证 |
| 文档 / 网页 / RAG | 限大小、净化、来源元数据和“不可信数据”隔离 | 将正文中的指令视作系统指令或编造引用 |
| PHI / 临床资料 | 最小化、服务端加密、tenant/actor/session 绑定、PHI-free Trace | 写入日志、评测集、Qdrant 正文、前端 bundle 或不必要第三方 |
| Agent / tool 输出 | 严格 schema、Runtime policy、预算、超时与安全后处理 | 未验证输出直接执行工具、持久化或作为医疗结论展示 |

## 7. Agent-Legible Invariants

1. 浏览器只连 BFF；所有外部 Provider 只能由服务端 services/provider adapter 调用。
2. 任何不可信输入都先验证、限长、隔离，再进入下一层；失败按风险 fail closed。
3. 未通过 schema 与 Runtime policy 的模型输出不得调用工具、写入数据库/Memory 或作为医疗结论展示。
4. 临床高风险行为默认 fail closed；未审核规则、未获授权或未获人工批准时不得生成可执行处方、药物调整或确定性诊断。
5. Trace、日志、评测和向量库默认不保存不必要的 PHI、凭据、用户原文或隐藏推理。
6. 前端页面、静态数据和安全降级不是后端业务完成证据；功能完成需要代码、测试和真实运行证据同时成立。

## 8. 模块状态

| 模块 | 当前真实能力 | 关键限制 |
|---|---|---|
| `agent_harness` | AgentScope ReAct、SSE、模型 failover、取消、医疗安全后处理 | 多智能体临床复核与临床副作用 workflow 未接入 |
| `workflows` | Chat workflow 的版本、责任模块、允许上下文和 workflow 风险档案注册 | 不是工作流执行器；临床副作用恢复、补偿与批准后执行未接入 |
| `runtime` | Capability registry、ALLOW/DENY/ASK、预算、审批与 checkpoint 契约 | 临床恢复 executor 未启用 |
| `rag` | 本地知识库摄取、混合检索、重排、引用与 Agent 工具 | 专项质量/安全评测缺口见矩阵 |
| `memory` | 加密会话事实、健康画像与无 PHI 语义引用 | 正式身份授权和生命周期治理未完成 |
| `search` | AnySearch 优先、Tavily 兜底、SSRF 与不可信内容隔离 | 不应替代本地循证证据 |
| `skill` | 声明式注册、版本、会话选择与 AgentScope viewer | 只允许受控 Markdown/ZIP；不执行上传代码 |
| `input_output` / `document` | BFF 的 ASR/TTS 与 MinerU 真调用；文档会话登记 | FastAPI adapter 和完整受控文件生命周期未完成 |
| `cga` | PHQ-9/SAS/PSQI 确定性评估；版本绑定题干/选项音频 | 不等于完整 CGA 或医生临床结论 |
| `prescription` | 受限临床信息收集 | 不是处方生成或用药审查；等待医学审核内容与授权 |
| `evals` | 合成、人工审阅的确定性安全 golden case | 不回放真实输入；模型/RAG/医疗评测尚缺 |

## 9. 前端与适老化架构约束

患者端老年模式默认开启，关键正文原则上不低于 18px、主要操作不小于 48px、图标必须具有可见文字或等价可访问名称。窄屏收起侧栏并以覆盖面板展示任务；桌面保留三栏任务流。所有异步操作应显示稳定、可理解的 loading / elapsed-time / error / retry 状态，且不能以频闪或不可取消音频制造“卡死”感。

CGA 题干和选项按 `scale_id + definition_version` 映射至 `apps/mvp/public/audio/cga/` 的预录制 WAV；实时 TTS 仅作受控兜底。播放必须可暂停、继续和停止；自动朗读只在患者老年模式的明确设置开启时针对新题目尝试一次。

## 10. 可扩展性与性能边界

应用服务以无状态请求处理为目标；持久化状态位于 PostgreSQL，短暂 ownership/限流/取消位于 Redis，向量数据位于 Qdrant，索引由独立 one-shot job 执行。会话 fencing、owner lease、有界 SSE queue、超时、预算与幂等键是横向扩展的基础，不是已经完成千级验证的证明。

当前只有 Docker Compose 中 **10 并发确定性高风险短路 SSE** 的真实证据；结果不能外推到模型、RAG、临床 workflow 或千级并发。面向 1,000 活跃连接的拓扑、背压、分阶段压测和放量门槛见[容量与扩展计划](docs/design-docs/容量与扩展计划.md)：它是设计基线，不是压测结论。最终发布前仍需补齐完整 ≤10 并发场景和空卷 Docker smoke。

## 11. 验证与变更

变更必须同步相应模块契约、测试、风险记录、[需求矩阵](docs/REQUIREMENTS_MATRIX.md) 与 active exec-plan。前端变化至少执行受影响的 lint/build 和真实 headless 关键路径；服务端契约、权限或持久化变化需要对应单元/集成测试和迁移验证。仅在所有必要功能实现并联调后，才执行全量门禁与最终 Docker 交付。

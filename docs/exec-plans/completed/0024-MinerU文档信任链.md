# 0024 — MinerU 文档信任链与受控上下文

> 创建：2026-07-16 | 优先级：P0 | 状态：已完成 | 前置：0022 前端真实解析链路

## 1. 目标

把已真实调用 MinerU 的 PDF/DOCX 解析结果从浏览器临时预览，升级为可验证主体归属、可撤销、可审计且不会执行文档内指令的受控文档上下文。不得把患者文档写入现有公共医学知识库，也不得在未经明确绑定的情况下传给模型。

## 2. 已审计事实

- `apps/mvp` 的 `POST /api/mineru/parse` 已完成 MinerU 签名上传、轮询、Markdown 下载和 Provider URL allowlist；实施开始时 Markdown 仅保存在浏览器组件状态供预览。
- FastAPI `ChatRequest.uploaded_files` 已是 UUID 引用契约，但 `ProductionAgentHarness.assemble_context()` 会拒绝任何非空列表；前端也固定发送空数组。
- 现有 `modules/rag` 只索引本地医学知识库，Qdrant payload 没有用户/租户文档的隔离字段，不能复用来存放病历、检查报告或个人上传内容。
- `SECURITY.md` 要求文档内容不可信、以固定边界标记隔离；敏感健康内容不得写入日志、Trace 或浏览器持久化。

## 3. 待确认的产品/隐私决策

受控上下文意味着把 MinerU 返回的 Markdown 从浏览器传到 FastAPI 并以 AES-256-GCM 加密保存。访客模式没有账户级长期授权或既有的文档保留期限规范，以下选择会直接影响隐私边界和数据模型，不能擅自决定：

1. **会话临时保留（已采用安全默认值）**：文档仅绑定当前 `tenant + actor + chat session`；用户移除附件或会话删除时立即不可检索并删除。独立 TTL 清理任务仍是后续项，未实现前不得把未主动删除的会话称为“定时清除”。
2. **账户长期保留**：允许跨会话使用，需另行定义登录身份、患者授权、保留/删除期限、医生访问控制和导出审计；不属于本变更集。

本计划只在选择 1 后实施阶段 A；选择 2 则先暂停文档上下文接入，转入账号/RBAC/保留策略设计。

## 4. 阶段 A（选择会话临时保留后）

1. 新建 `uploaded_documents` 加密表和 Alembic 迁移：保存受限文件元数据、解析 Markdown、解析来源、状态、所有者与 session；正文和原始文件名加密，唯一/索引字段不泄露 PHI。原始文件和内容摘要不入库。
2. 提供 Pydantic `extra="forbid"` 的登记、读取元数据、绑定/解绑和删除 API；每一次读取、绑定、检索和删除必须校验 `tenant_id + actor_id + session_id`。
3. 前端在 MinerU/本地文本解析成功后，经既有 BFF allowlist 显式登记并保存服务端 UUID；文件标签清楚展示“仅用于本次对话 / 已加入本次对话”，支持移除并撤销。不得使用 `localStorage` 保存正文或服务端文档 ID。
4. Chat 仅接受已登记、当前会话已绑定且未撤销的 UUID；Harness 读取受限长度、去除危险嵌入载体，并以 JSON 数据封装放入低优先级用户数据消息，文档不能伪造边界或改变系统优先级。模型工具与系统指令不得执行文档中的命令。
5. 初期不写入 Qdrant、embedding、日志或 Trace 的正文；以有界直接上下文实现文档问答。若需要跨文档/大文档语义检索，另建有租户围栏、删除语义、加密与泄漏评测的私有 RAG 计划。

## 5. 验收标准

- [x] Markdown 可登记、回读元数据并绑定本次聊天会话；Harness 单元测试验证 `uploaded_document` 引用与不可信边界。真实模型/RAG 依赖在本地浏览器中不可用，故浏览器未得到成功回答，不将其误称为完整文档问答成功。
- [x] 另一 actor 无法读取同一 UUID；同 session/actor 的 API、repository 和 Harness 都校验主体与会话。仍需补充另一 tenant 和另一 session 的集成回归。
- [x] 文档撤销后聊天不能再使用 UUID；真实 PostgreSQL 验证正文/文件名为加密列，撤销会擦除正文。Trace 正文不记录；仍需增加专门的 Trace 无泄漏回归。
- [x] 上传文档以不可伪造的 JSON 数据封装隔离为不可信材料；单元测试覆盖活跃 HTML、典型“忽略系统指令”文本移除及伪造结束标记，Harness 不执行其内容。
- [x] 前端无伪进度或持续旋转/闪烁；production 浏览器验证“发送时加入对话”→“已加入本次对话”、撤销 API、控制台 0 errors/0 warnings。
- [x] API/服务/迁移/前端必要测试、真实 PostgreSQL 迁移、headless production browser 流程和独立审阅均完成；文档已同步实际行为。

## 6. 非目标

- 不存储原始上传文件，不把私人文档放进公共医学知识库或当前 Qdrant collection。
- 不实现跨会话长期文档库、医生跨患者访问、长期保留、导出或面向大文档的向量检索。
- 不把文档内容视为医学证据；医疗答复仍须经过本地医学证据、安全规则和免责声明流程。

## 7. 实施记录

- 2026-07-16：完成前后端与 RAG 审计，确认 MinerU 解析已真实可用，但后端登记、所有权、会话绑定和 Harness 受控上下文均未实现。因个人健康文档的保留范围会改变隐私与权限边界，本计划进入待确认状态；在确认前维持当前“仅预览、不注入”的安全行为。
- 2026-07-16：按最小化会话级保留默认实现阶段 A：`a82c814f2022` 创建加密 `uploaded_documents`；`POST /documents`、会话范围读取和撤销 API 强制 JWT `document:read/write`、tenant、actor、session 围栏。撤销会覆盖加密正文；Harness 仅接受已登记 UUID、删除活跃 HTML 与典型注入行，并在低优先级 `UserMsg` 中将正文封装为不可伪造边界的 JSON 数据；不写入 Qdrant 或公共知识库。前端 BFF allowlist、Zod client 和会话标签已接通，跨会话会清空附件而不会自动重登记。
- 2026-07-16：必要验证已执行：单元 `23 passed`、ruff、mypy、前端 lint/build、Alembic upgrade/head/check 均通过；真实 PostgreSQL API 演练验证登记、跨 actor 404、撤销幂等、撤销后聊天拒绝及两列 `enc:v1:` 加密；production headless 浏览器验证 POST documents、chat 请求携带 UUID、DELETE 撤销、会话切换清空附件和 0 控制台错误。独立审阅修复并复核伪造文档边界、跨会话自动重登记与解析中竞态，最终无 P0/P1。浏览器回复因本地模型/RAG 依赖不可用而安全失败，不把该结果称为文档问答成功。
- 2026-07-16：在健康的标准 Compose API 栈与 production Next 前端中重新上传无敏感测试 PDF `mineru-real-e2e.pdf`。页面先稳定显示“正在解析文档”，随后显示“请提问后发送”；网络记录 `POST /api/mineru/parse` 为 200，响应确认 `success=true`、Markdown 非空（67 字符）。这再次证明真实 MinerU 签名上传、轮询和 Markdown 下载链路可用，不将其外推为模型回答成功。
- 2026-07-16：补齐文档解析取消控制。前端为每个解析维护独立 `AbortController`，取消后维持可重试的稳定失败态；BFF 把 `NextRequest.signal` 传给 MinerU 的签名、上传、轮询等待和 Markdown 下载。production browser 先实测同一无敏感 PDF 解析 `POST 200` 并显示“请提问后发送”，再实测上传后点击“取消解析”：网络记录为 `ERR_ABORTED`，BFF 日志为 `document parsing cancelled`，页面显示“已取消解析；如仍需要该文档，请点击重试”，控制台 0 error。`npm run test:document`、lint 和 production build 均通过。
- 2026-07-17：补齐会话级临时保留的删除出口：`DELETE /api/v1/sessions/{session_id}` 仅允许已验证 owner 删除空闲会话；运行中的 turn 返回 `409 CHAT_SESSION_ACTIVE`，避免与生成事务竞争。物理删除经数据库外键级联清除消息、`uploaded_documents`、临床收集、会话 Skill、审批与 checkpoint；PHI-free Trace 不含文档正文且不作为会话内容保留。Compose 实测创建访客会话、登记 `local_text` 文档、删除会话后消息和文档元数据接口均返回 404；`alembic check` 通过。

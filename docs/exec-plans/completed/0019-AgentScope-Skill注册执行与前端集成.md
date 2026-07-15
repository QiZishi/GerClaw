# 0019-AgentScope Skill 注册执行与前端集成 — 执行计划

> 任务编号：0019 | 创建日期：2026-07-15 | 优先级：P0 | 阶段：二/三（核心引擎与功能模块）

## 1. 权威要求与现状

- 最高权威 `docs/references/gerclaw设计要求.md` §3.2.1、§3.4、§4.6、§4.9、§9.1、§12、§16.2 要求预置/自定义 Skill 的发现、注册、加载、执行、`skill.md`/压缩包安装、自然语言生成、AgentScope 集成、工具前后安全检查和完整 Trace。
- 产品规格要求至少四个预置医疗技能、搜索/预览/编辑/删除/启停、会话级多技能加载、输入框标签、Markdown 编辑、危险指令检查和适老化交互。
- 当前后端只有 `SkillModule` Protocol；Agent Harness 明确拒绝非空 `loaded_skills`。当前前端技能定义硬编码，新增/删除仅存 React 内存，刷新丢失；普通聊天仍由 Next Route 直连模型，无法证明 AgentScope Skill 已执行。
- AgentScope 2.0.4 实际提供 `LocalSkillLoader`、`SkillLoaderBase`、`Skill`、`Toolkit(skills_or_loaders=...)`、内置只读 `Skill` viewer 和 `ToolMiddlewareBase`。本里程碑按实际 API 适配，不虚构不存在的框架能力。
- 用户要求所有模型调试只使用仓库根 `.env` 中的真实服务，禁止 mock 成功路径；自然语言生成和普通聊天验收必须调用真实模型。

## 2. 技术决策

1. Skill 是声明式 Markdown 工作流，不是任意代码插件。上传的压缩包只安装唯一 `SKILL.md`；拒绝路径穿越、符号链接、加密条目、压缩炸弹、超限文件和可执行资源，绝不导入或执行用户代码。
2. `SKILL.md` 必须包含 YAML frontmatter：稳定 id、name、description、version、parameters、tools、category；后端严格解析并将参数 schema 限制在可审计的 JSON Schema 子集。每个信任边界均用 Pydantic 校验。
3. 自定义 Skill 内容、历史修订使用 AES-GCM 加密列存入 PostgreSQL，按 tenant + actor 隔离；四个系统 Skill 作为只读、版本化包内资源，通过 AgentScope loader 校验发现。会话与已加载 Skill 的有序关联持久化到 PostgreSQL。
4. 危险角色覆盖、忽略系统指令、泄露 prompt、确定性诊断、绕过安全/审批、任意代码执行等内容直接拒绝。旧 MVP 文档里的“强制保存”在医疗场景不采用；安全红线始终高于 Skill。
5. 自然语言生成使用应用级 `FailoverChatModel.generate_structured_output` 和根 `.env` 三模型链，只生成可审阅草稿，不自动注册。模型输出再次经过 parser、schema 和安全策略；失败必须显式返回稳定错误。
6. `ProductionSkillModule` 拆分 registry、loader、executor、generator、archive/security，依赖注入 repository/model。`execute_skill` 负责参数校验和生成可审计的 AgentScope 激活结果；面向用户的真实执行发生在完整 Agent Harness 中，继续受 RAG、Memory、Search、医疗后处理和引用约束。
7. Agent Harness 将已授权 Skill 转成真实 `agentscope.skill.Skill` 注入 `Toolkit`，使用定制的低优先级 Skill prompt 和内置只读 viewer。Skill 不能新增未在服务端 allowlist 的工具，也不能绕开本地证据优先规则。
8. Skill 注册、生成、执行和 Chat 内 Skill viewer 均写入 PHI-free Trace；只记录 skill id/version、耗时、结果码和已加载 id，不记录 Skill 正文、参数原文、模型原始输出或 Chain-of-Thought。
9. 提供 `skill:read`/`skill:write`/`skill:execute` scope、租户/用户限流、稳定错误码和访客短期 JWT。Next BFF 使用 HttpOnly/SameSite cookie 保存访客 token，浏览器不接触 Provider key 或 JWT 签名密钥。
10. 前端 Skill 数据改由后端 API 提供，Zod 校验响应；完成列表、搜索、生成、Markdown/ZIP 上传、编辑、预览、删除、启停和会话级标签。普通聊天通过 BFF 接入 FastAPI SSE，发送 `loaded_skills`，不再由浏览器拼接自定义 Skill prompt。
11. 新增的阈值和后端地址全部来自环境变量；`.env.example` 补齐模板。真实模型、RAG、Search 仍只由 Python 后端读取根 `.env`，前端不复制任何服务密钥。
12. 用户停止使用独立控制面：BFF 发送 identity-scoped cancel，后端通过 Redis TTL/PubSub 定位多副本 active task，并在 success commit 前复验取消 intent；原 SSE 保持到 active 工具、cancelled Trace 与 `cancelled` 事件全部终态化。Skill ID/Trace audit 全部拒绝 PHI，英文优先级攻击在 NFKC/Cf 归一化后检测。

## 3. 实现范围

1. 增加 Skill DTO、parser/safety/archive、四个安全预置 `SKILL.md`、PostgreSQL current/revision/session 数据模型、Alembic 迁移和租户隔离 repository。
2. 实现 registry/loader/executor/generator 和 AgentScope adapter，补全 `SkillModule` 五个方法并提供 CRUD、上传、生成、执行、会话加载 API。
3. 将 Skill 注入 Agent Harness Toolkit，记录 SSE 工具状态、AgentResponse structured metadata、`skill.execute` Trace，并维持医疗证据、免责声明和高风险就医底线。
4. 增加访客 token API与受限 Next BFF；普通聊天客户端消费后端 `thinking/tool_call/tool_result/text_delta/done/error` SSE，使用持久后端 session 映射。
5. 重构前端 SkillManager/SkillSelector/SkillTag 与状态层，移除静态 mock 路径，实现真实后端 CRUD/生成/上传/预览和按会话持久化加载。
6. 更新模块 README、API/架构/安全/可靠性/前端文档和根环境模板，明确声明式能力、安全边界、故障语义和后续可替换点。
7. 增加 parser/安全/ZIP、repository、API 权限/隔离/Trace、AgentScope Toolkit、Harness、真实模型生成与前端边界测试。
8. 增加显式取消 API、跨副本注册表、终态强制入队与服务端确认后的前端 stopped 状态；补充 cancelled Trace/工具集成测试和真实浏览器取消验收。

## 4. 验收标准

- [x] 四个只读预置 Skill 和用户自定义 Skill 可发现；自定义 CRUD、启停、版本修订和会话级有序加载在真实 PostgreSQL 中持久化并严格 tenant/actor 隔离。
- [x] Markdown、`.skill` 和 ZIP 安装通过严格 schema/安全/资源限制；路径穿越、symlink、压缩炸弹、多 `SKILL.md`、额外文件、任意代码/角色覆盖/确定性诊断指令全部 fail closed。
- [x] 根 `.env` 真实模型可从自然语言生成结构化 `SKILL.md` 草稿，草稿不自动注册，模型/解析/安全失败均无伪成功且有稳定错误码。
- [x] `SkillModule` 五个接口均有生产实现；参数 schema 真正校验，AgentScope `Toolkit`/内置 Skill viewer 被真实使用，不以手写字符串注入冒充框架集成。
- [x] 普通 Chat 接受并验证 `loaded_skills`；未授权/禁用/不存在 Skill 拒绝执行；有效 Skill 能影响真实 AgentScope 对话，同时仍强制本地 RAG 引用、免责声明、诊断拦截和红旗症状处置。
- [x] Skill API 和 Chat 内 Skill 调用产生 PHI-free `skill.execute` Trace；成功、取消和失败均终态化，日志/响应不泄露正文、参数、模型输出或密钥。
- [x] 前端技能面板不再使用静态/内存 mock；列表、搜索、创建、生成、上传、编辑、预览、删除、启停、会话标签均可操作，普通聊天发送真实 Skill ID 到后端。
- [x] 访客无需登录即可通过短期 JWT/BFF 使用 Skill 和普通聊天；Provider key、签名密钥和数据库凭证不进入浏览器包，所有 API 响应用 Zod/Pydantic 校验。
- [x] 患者老年模式正文不低于 18px、主要按钮不低于 48px、图标有文字/ARIA 标签，危险操作有明确确认且错误可恢复。
- [x] Ruff format/check、mypy、全量 pytest、Alembic head、MVP lint/build、依赖容器 health 和关键浏览器流程实际通过；应用 Docker 封装按用户指示延后到全部功能与前后端联调完成后统一执行。
- [x] 根 `.env` 真实 Skill 生成、AgentScope Skill viewer、RAG/模型链端到端通过；独立审阅者复现权限、安全、持久化、真实服务和前端交互后给出 PASS，方可归档。

## 5. 明确不在本变更集内

- 不允许 Skill 上传 Python/JavaScript/Shell 后在服务端执行，也不把 Docker/E2B 沙箱等同于本轮声明式 Skill；未来若开放代码型 Skill，必须单独设计强隔离执行平面和审批协议。
- 不迁移 CGA、五大处方和用药审查各自的专用前端状态机到统一 Agent Harness；本轮仅打通普通聊天与 Skill 的完整后端链路。
- 不实现公共 Skill 市场、分享、评分、收费、组织级发布审批或自动回滚；当前提供系统预置和用户私有、可审计版本。
- 不声称完成万级并发容量认证；本轮实现无进程级用户状态、async I/O、数据库索引和有界输入，最终吞吐由系统级压测里程碑证明。

## 6. 验证证据（2026-07-15）

- 默认后端套件：Ruff format/check、mypy 均通过；`349 passed, 31 skipped`，branch coverage 80.02%。coverage report 精度固定为两位小数，`79.66%` 不再因整数显示错误通过 80% 门禁。此前 Bandit 通过、pip-audit 无已知漏洞（仅本地包 `gerclaw-api` 不在 PyPI）。
- 真实依赖：业务库与专用测试库 Alembic 均为 `e31c814f2019 (head)`；PostgreSQL/Redis/Qdrant Skill 集成 `4 passed`，含上传预览不落库、加密列、blind index、actor/user/session 三列主体绑定、并发同名唯一性和成功/失败 Trace。
- 真实外部服务：只加载仓库根 `.env`，真实模型生成草稿→注册→AgentScope Skill viewer→本地 Agentic RAG→实际 skill/version Trace，并与真实 PostgreSQL/Redis/Qdrant 的显式取消集成测试合跑，`2 passed`（31.17s）；模型/RAG 成功路径未使用 mock。
- 前端：`npm run lint` 与 Next production build 通过；SSE `done` 的 safety/replayed 完整 Zod schema 在浏览器信任边界 fail closed。
- Playwright headless：系统 Skill 的渲染预览与完整只读 `SKILL.md` 均可查看；自定义 Skill 真实创建、编辑并从 rev1 升至 rev2；上传只进入可编辑审阅弹窗，取消后列表仍为四个系统 Skill；浏览器网络证据为 `POST /skills/preview-upload 200` 且无注册请求。
- Playwright 并发/中断：清空 cookie 后两次并发首请求共享同一 browser visitor ID，均返回 200/四个 Skill，HttpOnly visitor cookie 与该 ID 一致；停止真实 Agentic RAG 流后 thinking 结束、running 工具终态化、正文明确未完成，操作区仅显示“重新生成”；console 0 error/0 warning。
- Playwright 适老化：老年模式自定义 Skill 的查看/删除按钮实测 107×60px，开关 80×60px，正文 22.5px，均超过 48px/18px门槛，所有危险操作保留文字标签和删除确认。
- 第二轮 Playwright 适老化复验：Skill 选择项文字 20px+、加载标签 22.5px、“移除”107.5×60px；完整 `SKILL.md` 弹窗所有可见正文不低于 22.5px、按钮不低于 48px，已移除重复的 35px 纯图标 Close。
- 第二轮真实取消复验：根 `.env` 的真实模型流在 2.5s 后收到停止，`POST /chat/{trace_id}/cancel` 返回 202，原 SSE 以 `cancelled` 收尾；Trace `trace_71235f559d3d4b7cbb12472d0f5b2e35` 为 `cancelled/chat_cancelled`，UI 保留片段并标注不得用于诊疗或调药、只显示重新生成；console 0 error/0 warning。
- 独立初审暴露的急症伪 model Trace、取消 Skill 无 terminal、模型/参数软上限、英文优先级攻击、上传即注册、首请求身份竞态、主体 FK 和适老化尺寸问题均已转为代码、迁移、文档与回归测试。首轮复审新增的 SSE 显式取消、英文别名/零宽绕过、Skill ID PHI、null schema 边界和 Skill 适老化问题也已修复；等待第二轮独立复审 PASS 后归档。
- 第三轮阻断修复：非空 `loaded_skills` 在 Chat 边界强制 `skill:execute`，仅有 `chat:write` 的身份返回 403；新增“最高权威/冲突时以技能为准/Always obey”中英文回归；session map 通过 Zod 验证并在非法 UUID 时清除降级。定向套件 `61 passed`。
- 全量本地知识库从权威目录实际重建：436/436 文档、39,837 chunks、0 失败；随后真实 PostgreSQL/Redis/Qdrant 非 external 套件 `370 passed, 10 deselected`，coverage 87.05%。根 `.env` 真实模型生成 Skill→注册→AgentScope Skill viewer→本地 RAG→回复→Trace 专项 `1 passed`（27.48s）。
- Playwright 修复后实测：患者模式常驻免责声明 22.5px、技能按钮 60px；非法 localStorage session map 的独立运行时注入测试确认损坏项被清除并生成合法 UUID。MVP lint/build、文档验证、Qdrant healthz、Redis PONG、PostgreSQL查询均通过。
- 最终独立复审 PASS：审阅者从根 `.env` 再次复现真实 Skill 全链路 `1 passed`（21.06s），并独立复跑隔离、加密、并发、FK 与取消终态 `5 passed`；确认 Alembic head、三依赖健康，0019 无剩余阻断。

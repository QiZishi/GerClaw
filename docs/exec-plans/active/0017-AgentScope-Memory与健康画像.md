# 0017-AgentScope Memory 与健康画像 — 执行计划

> 任务编号：0017 | 创建日期：2026-07-15 | 优先级：P0 | 阶段：二（核心引擎）

## 1. 权威要求与现状

- 最高权威 `docs/references/gerclaw设计要求.md` §4.2.5、§4.8、§8、§12、§14、§16.2 要求短期会话记忆、长期用户画像、相关性召回、上下文压缩、PostgreSQL JSON/加密存储、Qdrant 向量检索和可替换的 `MemoryModule`。
- AgentScope 2.0.4 提供 `Mem0Middleware`、`ContextConfig`、`Agent.compress_context()` 和 `AgentState`；项目现有 Memory 只有 Protocol，占位测试未覆盖任何真实行为。
- 0016 已把加密会话消息作为 PostgreSQL 事实源，并用每 turn 隔离的 `AgentState` 进入 AgentScope。当前只截取固定条数历史，不会跨会话召回健康画像，也不会保存压缩摘要。
- 用户要求模型与 embedding 调试只使用仓库根 `.env` 的真实服务，功能实现阶段不得用 mock 成功路径。

## 2. 技术决策

1. 复用 AgentScope `Mem0Middleware` 的自动召回、记忆工具和 middleware 生命周期，并通过其预构建 async client 扩展点注入 GerClaw Memory adapter；不自研第二套 Agent 循环。
2. 不采用 mem0 默认 SQLite/明文 payload 作为事实源：GerClaw 的结构化画像与事实保存在 PostgreSQL AES-256-GCM 加密列，Qdrant 仅保存 embedding、事实 UUID、版本和 HMAC tenant/user namespace，不保存用户文本或原始身份。
3. 短期记忆直接读取现有加密 `messages` 表；长期画像按用户跨会话共享。记忆检索必须先以 Qdrant 召回引用，再回 PostgreSQL tenant/user scoped 解密并校验版本，防止越权、悬空或 stale vector 被注入 prompt。
4. 画像抽取只读取用户自述，不从 assistant 回复反向写入事实；使用根 `.env` 的三模型 failover 执行严格结构化抽取。每条事实必须携带用户原文中的精确 `evidence_span`；无法逐字验证的模型候选直接丢弃，低置信度、否定或纠正信息只进入 pending/inactive，不作为已确认医疗事实注入。
5. 过敏、用药、慢病、生命体征、评估、重大事件和社会支持使用固定 schema、稳定 dedupe key、来源与时间戳；停药/失效信息保留历史而非物理删除。
   普通事实以 category/entity HMAC key 去重；事件按发生时间或 source Trace/evidence hash 分代。当前事实原地投影的每次变更前，必须在同一事务写入完整加密 revision snapshot。
6. 使用 AgentScope `ContextConfig` 和 `Agent.compress_context()` 生成医疗定制摘要，始终保留过敏、当前用药、红旗事件与最近对话；摘要写入 session 加密 `context_summary`，下一 turn 继续使用。
7. assistant、completed Trace、画像/事实更新和 `memory.update` 审计事件共享 0016 的 request-scoped 事务；任何模型抽取、向量索引或一致性校验失败都不得生成伪完成终态。Qdrant 失败或数据库回滚时执行有界补偿并由 stale-version 校验兜底。
8. 提供当前用户健康画像读取和事实确认/纠正接口，使用独立 `memory:read`/`memory:write` scope；所有写入使用乐观版本与 tenant/actor ownership 校验。

## 3. 实现范围

1. 扩展 Memory DTO/Protocol，实现短期记忆、长期画像、真实模型抽取、AgentScope 上下文压缩、画像合并和 prompt 安全投影。
2. 增加 memory facts PostgreSQL schema、索引、版本/状态/来源字段和 Alembic 双向迁移；保留现有 `health_profiles` 为用户级加密权威快照。
3. 实现独立 Qdrant memory collection、无 PHI payload、dense 检索、HMAC namespace、版本校验、upsert/delete 补偿和就绪检查。
4. 实现 AgentScope `Mem0Middleware` client adapter，将 `search_memory`/`add_memory` 与 GerClaw MemoryModule 对接；工具参数、结果和错误边界全部强校验。
5. 将长期画像、相关记忆、压缩短期历史接入 `AgentContext` 和 Agent system prompt/toolkit；完整 Memory 状态按 turn 隔离，不使用进程内用户单例。
6. 将画像抽取和 `memory.update` Trace 纳入 Chat 成功原子事务；重放不得重复抽取或重复写入事实。
7. 增加 `/api/v1/memory/profile` 与事实确认/纠正 API、强类型响应、权限、限流和稳定错误码。
8. 增加单元测试、真实 PostgreSQL/Redis/Qdrant 集成测试和根 `.env` 外部测试；真实测试覆盖跨会话召回、结构化画像、压缩与三模型/embedding 调用。
9. 更新 Memory/API README、架构、安全、可靠性、指标和 `.env.example`，记录 AgentScope 扩展点与一致性边界。

## 4. 验收标准

- [x] `MemoryModule` 五个方法都有生产实现、独立注入边界、严格类型和失败路径测试，覆盖率不低于 80%。
- [x] 同一用户在新会话能召回上一会话明确自述的过敏/用药/慢病；另一 tenant 或 actor 无法通过 API、Qdrant filter、猜测 UUID 或 stale point 读取。
- [x] PostgreSQL 中画像/事实/摘要均为密文；Qdrant payload、Trace、日志和错误响应不包含用户文本、姓名、手机号、证件号、药物/疾病事实明文。
- [x] 真实模型抽取只接受用户原文可验证的 evidence span；assistant 幻觉、否定句、停药/更正和冲突事实不会被错误提升为 active 事实。
- [x] 长对话实际触发 AgentScope `ContextConfig` 压缩，过敏、当前用药、红旗事件和最近消息保留，压缩摘要可跨进程恢复且原始消息仍可追溯。
- [x] `Mem0Middleware` 自动召回及 `search_memory`/`add_memory` 工具走 GerClaw adapter；不存在第二套自研 ReAct 或独立 mem0 SQLite 事实源。
- [x] Chat 成功提交与 memory update/Trace 一致；失败、断线、重放、并发会话和 Qdrant/模型故障不产生重复、半提交或错误已确认画像。
- [x] 根 `.env` 的真实三模型和 SiliconFlow embedding 完成跨会话记忆端到端测试，无 mock 成功路径。
- [x] Ruff format/check、mypy、Bandit、pip-audit、Alembic 全新库双向迁移、全量 pytest、Docker build/health、MVP lint/build 全部通过。
- [ ] 独立审阅者复现安全、并发、隐私和真实调用关键链路并给出 PASS 后提交和归档。

## 5. 执行证据

- 默认测试 `238 passed, 21 skipped`，覆盖率 80.99%；真实 PostgreSQL/Redis/Qdrant 回归 `253 passed, 6 deselected`，覆盖率 88.26%。
- 根 `.env` 的 6 项外部用例均取得真实通过结果：全套一次为 `5 passed, 1 failed`，失败发生在新会话已召回 `memories=2` 后的供应商可见输出断流，系统按设计返回 `CHAT_MODEL_STREAM_INTERRUPTED`；该跨会话真实用例随后隔离重跑 `1 passed`。三套真实 LLM、Mimo ASR/TTS、SiliconFlow embedding/rerank、Tavily 和完整 Agentic RAG Chat 均未使用 mock 成功路径。
- PostgreSQL 全新测试库完成 Alembic `upgrade → downgrade → upgrade` 至 `e41b8c2a2017 (head)`；`memory_fact_revisions.snapshot` 原始列为 `enc:v1:` 密文，停药/拒绝前的旧状态、剂量和 source Trace 可恢复；Docker 镜像构建、迁移、`/health/ready` 通过。
- readiness 强制复验可在 Memory collection 被外部删除后重建；单进程锁与多副本竞争后复验保证初始化幂等；开发 collection 为 0 points、无 PHI payload，隔离的测试 collection 在 fixture 结束后不存在。
- Docker Hub OAuth 连续两次网络超时后，使用同一官方 Python 3.12 slim 镜像的 `public.ecr.aws/docker/library/python:3.12-slim` mirror 完成无缓存依赖安装与镜像构建；新镜像执行 migration 后 API、PostgreSQL、Redis、Qdrant 均 healthy，`/health/ready` 返回 436 文档、39,837 chunks、Memory 0 PHI points。
- 真实复验发现供应商持续流式心跳可绕过 HTTP read timeout；现以配置的 30 秒为每个候选模型完整 stream deadline。超时前无公开输出则顺序 failover，已有公开输出则 fail closed，测试覆盖两条路径。
- MVP `npm run lint` 与 `npm run build` 均通过；本变更未修改前端行为。

## 6. 明确不在本变更集内

- 不实现完整账号注册/登录、医生代患者授权和 FHIR/医院 HIS 同步；本轮沿用已验证 JWT opaque actor 映射。
- 不实现 Skill、Search、Voice、Document、处方或 CGA 业务模块；它们后续通过 Memory Protocol 写入已确认结构化事实。
- 不声称已经达到万级并发；本轮必须保持无进程内用户状态、异步 I/O、有界上下文和数据库/向量隔离，最终容量仍由完整系统负载测试证明。

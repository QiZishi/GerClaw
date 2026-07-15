# 0021 — Runtime Permission、HITL、Tool Registry 与复核

> 创建：2026-07-15 | 完成：2026-07-15 | 优先级：P0 | 状态：已完成

## 1. 目标

完成 `RUN-02/03/06/07` 的 Runtime 基础合同：所有已注册 Agent 工具只能通过统一 PermissionEngine 和 Tool Registry 执行；高风险动作具备可持久化审批、一次性凭证和 version-bound checkpoint 原语；执行预算与审批事件进入同一 PHI-free Trace。临床副作用恢复 executor 和多智能体复核不在本计划宣称完成。

## 2. 范围

1. 定义严格 Pydantic schema：主体/租户/患者/会话上下文、工具 capability、风险/副作用等级、ALLOW/DENY/ASK 决策、预算、checkpoint、审批和复核结果。
2. 实现 PermissionEngine：服务端 allowlist、scope/role/ownership/patient-consent、参数约束、网络/数据范围、风险规则和稳定拒绝码；prompt/UI 不承担授权。
3. 实现 Tool Registry：注册、版本、输入/输出 schema、超时、重试、熔断、结果大小、幂等 key、调用前/中/后验证；接管现有 RAG/Search/Memory/Skill 工具。
4. 实现 PostgreSQL HITL 状态机与 API：pending/approved/rejected/expired/cancelled、actor/reason/version、乐观并发、加密 checkpoint 和一次性副作用凭证。临床副作用恢复 executor 留待对应业务模块启用时接入。
5. 实现统一执行预算和 checkpoint：wall-clock、步骤、重试、tool/model calls、token、输出大小；超限稳定失败，checkpoint 版本不兼容 fail closed。
6. 接入 Chat SSE/Trace/metrics；审批 UI 将按用户优先级移至紧随本计划的前端整合计划。多智能体复核随临床 workflow 计划实现，不能以无真实业务动作的空壳替代。

## 3. 非目标

- 不在本里程碑实现 CGA、处方、用药、慢病或情感陪伴业务规则；只交付它们后续复用的 Runtime/HITL 基础。
- 不新增 Provider 或重写 AgentScope；优先适配现有 ReAct harness 与模块 Protocol。
- 不宣称完整生产 RBAC/患者授权；缺失角色/consent 时高风险动作必须 DENY/ASK，不能默认放行。

## 4. 验收标准

- [x] ALLOW/DENY/ASK、scope/tenant/actor/ownership/参数/网络/数据边界有正负向测试。
- [x] ASK 可跨请求读取；重复批准、过期、拒绝、取消和竞争更新不会重复发放副作用凭证。临床副作用恢复在后续业务 executor 中验收。
- [x] 所有已注册工具严格验证参数与结果；未注册/版本不兼容/超时/超限 fail closed。
- [x] 预算和 checkpoint 在超限、版本不兼容和重启加载下保持 fail closed；副作用 replay 在后续 executor 中验收。
- [x] 必要 unit/integration/external、coverage、lint/type/build、migration 和独立审阅全部 PASS。

前端 HITL 状态、患者模式字号/按钮、ARIA/键盘和浏览器审阅已明确转入 0022；临床副作用恢复 executor 与多智能体临床复核仍须在相应业务 workflow 中验收，均不属于本 Runtime 基础合同的完成声明。

## 5. 预定证据

- `scripts/quality-gate.sh backend` 与针对 Runtime/HITL 的精确 pytest。
- 专用 `_test` PostgreSQL/Redis/Qdrant integration，包含重启/竞争/幂等故障注入。
- 显式 opt-in 的真实模型→工具→Trace 用例；临床复核随对应 workflow 验收。
- 前端审批状态与浏览器证据移入紧随其后的前端计划。

## 6. 完成证据

- `scripts/quality-gate.sh backend`：`377 passed, 35 skipped`，coverage `80.04%`，Ruff、mypy（107 source files）与 Alembic head 均通过。
- `scripts/quality-gate.sh integration`：真实 PostgreSQL/Redis/Qdrant、正确的本地知识库挂载下 `402 passed, 10 deselected`，coverage `87.19%`；迁移 drift check 无新操作。
- `scripts/quality-gate.sh docs` 与 `scripts/quality-gate.sh security` 通过；安全扫描未发现已知依赖漏洞。
- 独立审阅确认无 P0/P1：一次性 permit 阻断直接工具调用、全执行周期 wall-clock watchdog、审批 Trace 持久化、服务端 schema 边界与审批复核读取均已覆盖。

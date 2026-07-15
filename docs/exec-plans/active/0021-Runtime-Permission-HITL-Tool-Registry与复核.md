# 0021 — Runtime Permission、HITL、Tool Registry 与复核

> 创建：2026-07-15 | 优先级：P0 | 状态：待开始

## 1. 目标

完成 `RUN-02/03/05/06/07` 的生产 Runtime 合同：所有 Agent/workflow 只能通过统一 PermissionEngine 和 Tool Registry 执行工具；高风险动作进入可持久化、可恢复的 HITL；执行预算、checkpoint、幂等副作用和多智能体复核进入同一 PHI-free Trace。

## 2. 范围

1. 定义严格 Pydantic schema：主体/租户/患者/会话上下文、工具 capability、风险/副作用等级、ALLOW/DENY/ASK 决策、预算、checkpoint、审批和复核结果。
2. 实现 PermissionEngine：服务端 allowlist、scope/role/ownership/patient-consent、参数约束、网络/数据范围、风险规则和稳定拒绝码；prompt/UI 不承担授权。
3. 实现 Tool Registry：注册、版本、输入/输出 schema、超时、重试、熔断、结果大小、幂等 key、调用前/中/后验证；接管现有 RAG/Search/Memory/Skill 工具。
4. 实现 PostgreSQL HITL 状态机与 API：pending/approved/rejected/expired/cancelled、actor/reason/version、乐观并发、恢复入口和一次性副作用凭证。
5. 实现统一执行预算和 checkpoint/replay：wall-clock、步骤、重试、tool/model calls、token、输出大小；超限稳定失败，重放不重复外部副作用。
6. 实现普通回答的老年专科复核链：主回答与复核意见责任分离，复核不能绕过安全/权限/证据门禁。
7. 接入 Chat SSE/Trace/metrics，并提供最小可用 HITL 前端等待/批准/拒绝/恢复状态；保持患者端适老化与医疗免责声明。

## 3. 非目标

- 不在本里程碑实现 CGA、处方、用药、慢病或情感陪伴业务规则；只交付它们后续复用的 Runtime/HITL 基础。
- 不新增 Provider 或重写 AgentScope；优先适配现有 ReAct harness 与模块 Protocol。
- 不宣称完整生产 RBAC/患者授权；缺失角色/consent 时高风险动作必须 DENY/ASK，不能默认放行。

## 4. 验收标准

- [ ] ALLOW/DENY/ASK、scope/tenant/actor/ownership/参数/网络/数据边界有正负向测试。
- [ ] ASK 可跨请求/重启恢复；重复批准、过期、拒绝、取消和竞争更新不会重复副作用。
- [ ] 所有已注册工具严格验证参数与结果；未注册/版本不兼容/超时/超限 fail closed。
- [ ] 预算和 checkpoint/replay 在取消、断流、lost acknowledgement 与进程重启下保持确定终态。
- [ ] 主回答→老年专科复核真实运行，引用、免责声明、安全决策和 PHI-free Trace 可追踪。
- [ ] 前端 HITL 状态真实接入，患者模式正文≥18px、按钮≥48px、ARIA/键盘/错误恢复通过浏览器审阅。
- [ ] 必要 unit/integration/external/e2e、coverage、lint/type/build、migration 和独立审阅全部 PASS。

## 5. 预定证据

- `scripts/quality-gate.sh backend` 与针对 Runtime/HITL 的精确 pytest。
- 专用 `_test` PostgreSQL/Redis/Qdrant integration，包含重启/竞争/幂等故障注入。
- 显式 opt-in 的真实模型主回答→复核→工具→Trace 用例。
- Playwright CLI 的 pending/approve/reject/expire/cancel/recover 状态与 computed style/ARIA/console 证据。

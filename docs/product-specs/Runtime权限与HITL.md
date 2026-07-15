# Runtime 权限与 HITL 产品规格

## 1. 用户价值

所有 Agent、Skill、workflow 和工具共享同一服务端授权路径。用户能理解某项动作为何允许、拒绝或等待医生审批；页面关闭、服务重启或重复请求不会让高风险动作越权或重复执行。

## 2. 决策合同

决策只有 `ALLOW`、`DENY`、`ASK`：

- `DENY` 优先级最高，包括未注册工具、版本不兼容、缺 scope/归属、禁止角色、未验证患者访问、PHI 外发和 critical 动作。
- `ASK` 用于经授权但存在副作用或临床高风险、且 capability 明确声明审批角色的动作；必须先持久化审批，不能由模型自批。没有审批角色的工具即使底层 AgentScope 要求确认，也 fail closed，不能被误当成医疗审批。
- `ALLOW` 只用于全部边界通过的低风险只读动作；默认行为不是 ALLOW。

任何 decision 都返回稳定 code、规则版本和 capability 版本，不回显 PHI、凭证或完整参数。

## 3. HITL 生命周期

`pending → approved/rejected/expired/cancelled` 为单向终态。审批记录绑定 tenant、请求 actor、患者/会话、tool/version、参数指纹、幂等 key、审批角色、过期时间和 revision。批准只生成一次性执行凭证；Runtime executor 必须在副作用开始前原子消费该凭证。当前已注册工具均为只读，尚未开放任何临床或外部写入 executor。

## 4. 预算与恢复

每轮固定 wall-clock、步骤、重试、模型/工具调用、token 和输出大小预算。checkpoint 持久化 schema/policy/tool/workflow 版本及加密状态；恢复前必须验证全部版本和状态指纹，不兼容时失败，不自动迁移成新的医疗行为。跨进程 continuation executor 将在后续临床副作用模块启用时接入，当前不会伪装为已执行的医疗动作。

## 5. 前端状态

患者端等待审批使用≥18px正文、≥48px带文字按钮，展示原因、审批角色、有效期、取消和恢复入口。批准/拒绝只能由拥有服务端 scope 且数据库角色匹配的身份执行；审批人通过受控 review endpoint 查看加密动作参数，UI 角色切换不改变权限。

## 6. 验收

- 三决策及优先级、跨租户/跨患者、版本、参数、PHI 和预算负向测试。
- 重启恢复、重复批准、并发竞争、过期、取消、lost acknowledgement 不重复副作用。
- RAG/Search/Memory/Skill 均通过注册表；未注册工具无法进入 AgentScope toolkit。
- Trace 只保存安全标识、decision code、版本、耗时和 outcome。

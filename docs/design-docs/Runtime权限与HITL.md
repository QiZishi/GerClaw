# Runtime Permission/HITL/Tool Registry 设计

## 1. 架构

```text
verified Auth/ownership/consent context
                │
                ▼
GerClaw PolicyEngine ── DENY/ASK/ALLOW + stable code
                │
                ▼
AgentScope PermissionEngine + governed ToolBase
                │
        ┌───────┴────────┐
      ALLOW             ASK
        │                │
Tool Registry invoke   PostgreSQL Approval
        │                │ approve token
schema/output/size     resume checkpoint
        └───────┬────────┘
          PHI-free Trace
```

GerClaw 层负责业务身份、患者、数据分类和临床风险；AgentScope 层负责工具自身安全判断与 ReAct 中断事件。最终决策取最严格值 `DENY > ASK > ALLOW`。生产禁止 `PermissionMode.BYPASS`。

## 2. 模块边界

- `modules/runtime/models.py`：严格 DTO、枚举、预算和 checkpoint 合同。
- `modules/runtime/permission.py`：确定性策略与 AgentScope decision 映射。
- `modules/runtime/registry.py`：唯一名称/版本、Pydantic 输入输出、大小/超时/幂等和调用生命周期。
- `repositories/approval.py`：tenant/actor/patient scoped 持久化和原子状态转换。
- `services/approval_service.py`：审批、一次性执行凭证和取消编排；临床副作用 executor 尚未启用。
- `api/routes/approvals.py`：只接受验证身份，不接收客户端角色或 tenant。

## 3. 安全不变量

1. 未注册、版本不符或 schema 不符在执行器之前失败。
2. `critical` 永远 DENY；`high`、写入和外部副作用默认 ASK；低风险只读才可能 ALLOW。
3. 外部网络工具声明会处理标识符/PHI 时，只有服务端证明已脱敏才可继续；凭证数据永不外发。
4. patient-scoped 工具必须由服务端 conversation/repository 已验证的归属构造 Runtime context；请求 body 的布尔值不构成证明。
5. 参数正文、approval reason、错误和 tool output 不进入 JSONB Trace；敏感审批 payload 使用 AES-GCM。
6. 每个副作用具有 tenant-scoped idempotency key 和 approval token；数据库唯一约束是最终防线。
7. checkpoint 只允许同 schema/policy/capability 版本加载；当前只读工具不存在可恢复副作用，未来 executor 必须在消费一次性凭证后才能继续。

## 4. 失败语义

策略拒绝返回稳定 code；ASK 先提交加密 approval，再发送 `approval_required` SSE，随后本轮以安全的待审批终态停止；超时/预算/版本/输出校验分别产生稳定失败。存储或 Trace 提交失败时不发 `done`，副作用工具必须先有可补偿/可查询的执行凭证。

## 5. AgentScope 适配

每轮从验证后的 Runtime context 构造 `PermissionContext(mode=DEFAULT)`；Tool Registry 只把当前允许发现的 governed tools 加入 `Toolkit`。工具自己的 `check_permissions` 仍执行，GerClaw 决策不能被 AgentScope allow rule 放宽。只有 capability 已声明 `approval_roles` 的 `RequireUserConfirmEvent` 才能转换为持久化 ASK；未声明的请求直接 fail closed，不会生成空审批。

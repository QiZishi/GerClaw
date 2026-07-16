# Runtime 模块

## 职责

`runtime` 是 Agent、workflow 与 AgentScope 工具之间唯一的服务端治理边界。它定义不可变 capability、主体和调用契约，执行预算、工具 schema/大小校验和 fail-closed 权限决策；下游 tool 不能绕过或放宽其 verdict。

## 已实现接口

| 组件 | 对外作用 |
|---|---|
| `models.py` | 严格、版本化 Pydantic DTO：`RuntimePrincipal`、`ToolCapability`、`ToolInvocationRequest`、`PermissionVerdict`、审批和 `ExecutionBudget` |
| `permission.py` | `RuntimePermissionEngine.evaluate()`：依据 scope、角色、患者访问、外发脱敏、风险等级、幂等键和 AgentScope verdict 返回 `ALLOW`、`DENY` 或 `ASK` |
| `registry.py` | `GovernedToolRegistry` 与 `GovernedTool`：把已注册的 AgentScope `ToolBase` 包装为 request-scoped allowlist，执行输入/输出 schema、字节上限、超时和 fresh permit 校验 |
| `budget.py` | `RuntimeBudgetTracker`：递增计量 steps、retries、model/tool calls、token、输出和 wall clock；超限抛出稳定的 `RUNTIME_*_EXCEEDED` 代码 |
| `tool_schemas.py` | 当前受 Runtime 包装的 RAG、Memory、Web Search 工具的严格输入 model |

所有 schema 都拒绝未知字段；capability 与 policy 版本由服务端注册，不接受浏览器或模型自报的角色、预算或权限。

## 决策与数据流

```text
服务器 capability 注册
  → Agent 产生 ToolInvocationRequest
  → Pydantic + 输入大小校验
  → AgentScope Permission + RuntimePermissionEngine
  → ALLOW / DENY / ASK
  → 有 fresh permit 才能调用 delegate
  → timeout、输出大小/类型校验、Trace 终态
```

- 未注册、版本不匹配、scope/角色不符、患者访问未验证、敏感数据未脱敏外发和 critical action 都会 `DENY`。
- high risk 或任何 side effect 均要求幂等键；非 critical 的高风险行为还必须由可交互上下文中的持久化审批进入 `ASK`。
- credential 数据永远不能注册给 external network tool。

## 配置、可观测性与限制

运行预算和 capability 是代码注册的版本化策略，不读取前端配置。审批持久化、Trace 与 checkpoint 由上层 service/repository 集成；本模块本身不记录用户自由文本或 PHI。

当前 `ASK` 的审批记录与一次性执行 token 已实现，但**临床副作用 workflow 的 resume executor 尚未启用**。因此不能因存在 `ASK` 或 approval API 就将临床执行、医生批准或患者授权表述为已完成。

## 验收与修改规则

修改本模块至少运行：

```bash
cd apps/api
uv run pytest -q tests/test_runtime_permission.py tests/test_runtime_registry.py tests/test_runtime_budget.py
uv run ruff check src/gerclaw_api/modules/runtime tests/test_runtime_permission.py tests/test_runtime_registry.py tests/test_runtime_budget.py
uv run mypy src/gerclaw_api/modules/runtime
```

改变 approval、审计或实际工具接线时，还必须运行相关 chat/approval 集成测试，并同步更新 capability 版本、风险记录和调用模块的 `AGENTS.md`。

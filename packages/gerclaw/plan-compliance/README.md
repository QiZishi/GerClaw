# GerClaw Plan 适配插件

本插件只补强 DSH 原生 Plan mode 的模型协作边界：当模型已输出带 Markdown 标题的计划、但没有调用原生 `exit_plan_mode` 时，通过 `agent/turn-stopping` 在同一 turn 内追加一次续步提醒。审批、批准、拒绝、状态持久化和恢复仍完全由 `@deepseek-ai/dsh-plan-mode` 负责。

插件注入 `planMode`，随 Agent preset 的隔离上下文加载。监听器由 Cordis `ctx.on()` 管理，Loader 禁用或热更新插件时自动移除。一次 turn 最多续步一次；检测到原生审核工具调用、非 Plan 状态或已存在本插件提醒时不会再次介入。

扩展时不要在本插件中保存 Plan 状态、生成审批卡或直接执行计划。验证应通过真实 GerClaw Profile 进入 Plan mode，并确认 Loader 禁用后不再续步、恢复后重新生效。

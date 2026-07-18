# Chronic Care

`chronic_care` is a real backend ledger for a user to record a self-reported
condition and timestamped measurements. The data is encrypted and bounded to
the authenticated tenant and actor. It can show the arithmetic direction
between the last two values of the same user-entered metric label.

The patient MVP exposes this ledger at **我的慢病记录** through the controlled
`/api/gerclaw` BFF: a user can create a self-reported label and append a
measurement, then read the owned ledger and arithmetic comparison. The UI
labels every condition as self-reported and never renders a clinical range,
target, diagnosis or treatment recommendation.

This is deliberately not a chronic-disease management conclusion. It has no
clinical thresholds, targets, alerts, medication assessment, reminder,
adherence inference, treatment suggestion, doctor queue or patient
authorisation workflow. Those capabilities require versioned medical evidence,
review and RBAC/HITL before they can consume this ledger.

## 维护与演进

**可安全改进。** 可完善测量单位规范化、时间序列查询、导入导出和医生授权后的只读投影；若新增阈值、目标、提醒或临床解释，必须先引入版本化规则来源、审核者、适用人群和撤回策略。

**不可破坏的契约。** 账本必须继续按 tenant/actor 加密隔离；趋势只能是同一自定义指标最近两个值的算术比较，不能暗示正常范围、病情好坏或调药。不得把自述标签提升为诊断，也不得通过列表或错误信息枚举他人数据。

**性能与回归验收。** 必测 owner 隔离、相同时间戳的稳定追加顺序、单位/数值边界、重复写入与历史分页；10 个主体并发写入时，各自最新值和趋势必须可重复且无交叉。新增查询应给出测量数增长下的 p95、索引计划和加密开销。

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

A logged-in patient may additionally grant one named doctor
`chronic_care_read`. After the consent repository verifies that grant at read
time, the doctor workbench can list the patient's self-reported conditions and
read their measurements plus arithmetic directions. This is a narrow read
projection: it does not disclose chats, uploads, Trace, alerts, assessment
answers or other records, and it never permits a doctor to create, edit or
clinically interpret a ledger entry.

This is deliberately not a chronic-disease management conclusion. It has no
clinical thresholds, targets, alerts, medication assessment, reminder,
adherence inference, treatment suggestion or doctor queue. Those capabilities
require versioned medical evidence, review and RBAC/HITL before they can
consume this ledger.

## 维护与演进

**可安全改进。** 可完善测量单位规范化、时间序列查询、导入导出和患者授权后的医生只读投影；若新增阈值、目标、提醒或临床解释，必须先引入版本化规则来源、审核者、适用人群和撤回策略。

**不可破坏的契约。** 账本必须继续按 tenant/actor 加密隔离；趋势只能是同一自定义指标最近两个值的算术比较，不能暗示正常范围、病情好坏或调药。`chronic_care_read` 必须逐次验证患者→指定医生→期限→revision，且只能返回该最小只读投影。不得把自述标签提升为诊断，也不得通过列表或错误信息枚举他人数据。

**性能与回归验收。** 必测 owner 隔离、同时间戳的稳定追加顺序、单位/数值边界、重复写入与历史分页，以及授权前/撤回后/到期后的医生拒绝；10 个主体并发写入时，各自最新值和趋势必须可重复且无交叉。新增查询应给出测量数增长下的 p95、索引计划和加密开销。

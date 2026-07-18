# Risk Alert

`risk_alert` is the deterministic, caller-owned alert ledger for safety signals
already established elsewhere in the backend. Supported sources are CGA
immediate-safety/high-follow-up signals, server-detected chat red flags, and
only contraindicated or major hits from the deterministic medication-rule
review. Medication alerts contain no drug name, dose, rule text or source
locator; those remain in the clinician/pharmacist review artifact.

The module stores no questionnaire text, answer, assessment ID, user text or
identifier in an alert. A keyed source fingerprint deduplicates a signal, while
the alert's kind, severity and fixed guidance are encrypted. The API exposes
only the authenticated owner's alert list and an idempotent acknowledgement;
acknowledging does not dismiss an alert or change its urgency.

It is deliberately not a clinician notification, emergency dispatch, diagnosis,
or a replacement for medical care. A patient may explicitly grant a named doctor
the read-only `risk_alert_read` scope; the doctor then sees only this alert
ledger through the restricted workspace, never source chats, assessment answers,
medication lists, attachments or Trace data. Human escalation and contact
notifications remain outside this read-only boundary.

The patient UI exposes **我的安全提醒** through a strict BFF allowlist. It
shows only this caller's server-determined alerts and can submit the existing
revision-fenced acknowledgement. The button says “我已了解此提醒”, never
“解除” or “关闭”: acknowledgement is not a clinical resolution or an external
notification. Active critical alerts are ordered before active high alerts, so
an immediate-safety reminder cannot be visually buried by a newer follow-up.

For operational visibility, `gerclaw_risk_alerts_total` counts only the bounded
source (`cga`, `chat` or `medication_review`), severity and lifecycle outcome (creation,
deduplication, acknowledgement or idempotent acknowledgement replay). It intentionally has no patient, alert,
assessment, session, free-text or guidance label.

## 维护与演进

**可安全改进。** 可新增已定义来源的确定性告警、展示可达性和患者授权的只读医生投影；通知、人工升级或临床队列须另建明确的责任人、联系策略、重试与审计流程，不能从 ledger 自动推断。

**不可破坏的契约。** alert 只记录已由来源模块确定的信号，必须保持 source fingerprint 去重、加密载荷和 owner scope；“已了解”不等于解除/关闭。医生仅可在有效 `risk_alert_read` 下读取投影，绝不返回聊天、答案、用药、附件或 Trace。

**性能与回归验收。** 覆盖 source 去重、critical 排序、幂等 acknowledgement、跨主体拒绝、授权/撤回与无敏感字段投影；Chat/CGA/用药严重命中需各有生成回归。10 并发同源写入应只产生一个 active alert，列表读取 p95 与 dedup 冲突数需记录。

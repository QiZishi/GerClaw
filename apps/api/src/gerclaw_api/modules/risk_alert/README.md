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

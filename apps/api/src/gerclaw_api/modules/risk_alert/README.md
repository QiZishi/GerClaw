# Risk Alert

`risk_alert` is the deterministic, caller-owned alert ledger for safety signals
already established elsewhere in the backend. The first supported source is
CGA: immediate safety assessment and high-severity follow-up signals returned
by the server-owned scale workflow.

The module stores no questionnaire text, answer, assessment ID, user text or
identifier in an alert. A keyed source fingerprint deduplicates a signal, while
the alert's kind, severity and fixed guidance are encrypted. The API exposes
only the authenticated owner's alert list and an idempotent acknowledgement;
acknowledging does not dismiss an alert or change its urgency.

It is deliberately not a clinician notification, emergency dispatch, diagnosis,
or a replacement for medical care. Cross-patient queues, human escalation and
contact notifications remain blocked on the account/RBAC/authorisation plan.

For operational visibility, `gerclaw_risk_alerts_total` counts only the bounded
source (`cga` or `chat`), severity and lifecycle outcome (creation,
deduplication, acknowledgement or idempotent acknowledgement replay). It intentionally has no patient, alert,
assessment, session, free-text or guidance label.

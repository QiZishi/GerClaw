# Risk Alert Module Instructions

## Responsibility

This module persists and exposes the caller-owned, deterministic risk-alert
workflow. It accepts only typed signals emitted by already-authoritative server
rules; it does not diagnose, score a questionnaire, infer risk from free text,
or make a clinical recommendation.

## Invariants

- A risk alert is tenant- and actor-scoped. A doctor may read a patient's alert
  ledger only through the explicit `risk_alert_read` consent scope plus the
  ordinary `risk_alert:read` role scope; it is never a notification, write or
  emergency-dispatch authority.
- The source identity is a keyed fingerprint. Do not store assessment IDs,
  question IDs, answers, free text, or user identifiers in alert metadata.
- Risk kind, severity and user-facing guidance are encrypted at rest. Read
  routes return only the authenticated caller's validated alert projection.
- Prometheus may record only the bounded `source`, `severity` and lifecycle
  `outcome`; it must never use any owner, alert, assessment, session, question,
  answer or text value as a metric label.
- Deduplication is deterministic per source signal. Acknowledgement is
  idempotent and revision-fenced; it never resolves or downgrades a risk.
- Alert creation is a persistence side effect of a deterministic source state,
  not an LLM/tool action. It must share the source transaction where possible.
- The current typed sources are CGA, chat red flags and only
  `contraindicated`/`major` hits from the deterministic medication rules.
  Medication alerts contain fixed guidance only: medication names, doses,
  source locators and rule text remain exclusively in the clinician-review
  artifact.
- List results must be safety-first: active `critical` alerts precede active
  `high` alerts, regardless of database recency or identifier order.

## Change and test rules

- Add every new source as a typed signal with policy version, source fingerprint
  and boundary tests. Never accept a client-provided severity or action.
- Preserve the medical disclaimer and urgent-care wording. Notifications,
  emergency dispatch and clinician escalation require separate approved contact
  and authorisation workflows; do not claim them here.
- Test owner isolation, dedupe, idempotency, stale revisions and encrypted
  persistence before connecting a new source.

# Risk Alert Module Instructions

## Responsibility

This module persists and exposes the caller-owned, deterministic risk-alert
workflow. It accepts only typed signals emitted by already-authoritative server
rules; it does not diagnose, score a questionnaire, infer risk from free text,
or make a clinical recommendation.

## Invariants

- A risk alert is tenant- and actor-scoped. There is no cross-patient or
  clinician queue until account, RBAC and patient authorisation are complete.
- The source identity is a keyed fingerprint. Do not store assessment IDs,
  question IDs, answers, free text, or user identifiers in alert metadata.
- Risk kind, severity and user-facing guidance are encrypted at rest. Read
  routes return only the authenticated caller's validated alert projection.
- Deduplication is deterministic per source signal. Acknowledgement is
  idempotent and revision-fenced; it never resolves or downgrades a risk.
- Alert creation is a persistence side effect of a deterministic source state,
  not an LLM/tool action. It must share the source transaction where possible.

## Change and test rules

- Add every new source as a typed signal with policy version, source fingerprint
  and boundary tests. Never accept a client-provided severity or action.
- Preserve the medical disclaimer and urgent-care wording. Notifications,
  emergency dispatch and clinician escalation require separate approved contact
  and authorisation workflows; do not claim them here.
- Test owner isolation, dedupe, idempotency, stale revisions and encrypted
  persistence before connecting a new source.

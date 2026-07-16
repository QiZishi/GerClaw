# Companion Module Instructions

## Responsibility

This module owns the policy contract for the safety-first emotional-companion
workflow. It is a supportive AI conversation mode, not a medical, crisis,
therapy, human-relationship, notification, or long-term-memory module.

## Invariants

- The companion identifies as AI; it must not impersonate a human, relative,
  clinician or emergency service, promise proactive contact, or encourage
  exclusivity, secrecy, guilt or emotional dependency.
- Long-term health Memory, RAG, web search, Skills and uploaded documents are
  disabled. Only caller-scoped, encrypted short-term session conversation may
  be used as context.
- Existing deterministic high-risk detection always runs before a model and
  must keep its emergency short-circuit, disclaimer and risk-alert behavior.
- Companion mode emits no diagnosis, treatment, clinical risk score, or claim
  that it has contacted a person or service.

## Change and test rules

- Keep the prompt concise and behavior-oriented; do not impose arbitrary output
  length, fixed formatting, or repeated self-review.
- Any new memory, crisis escalation, notification or clinical behavior requires
  its own reviewed contract, authorization model, persistence boundary and
  regression tests.

# Workflow Module Instructions

## Responsibility

This module owns the server-side registry for executable GerClaw workflows.
It records workflow version, owner, allowed context and reviewed security-risk
profile before a workflow can enter the Runtime Harness.

## Invariants

- Browser input may select only a registered workflow; it cannot provide a
  version, owner, risk level, permissions or context allowance.
- Each enabled workflow must have an exact active `security_evaluation`
  workflow profile with matching version, owner, risk, network and data class.
- Companion never accepts Skills, uploaded files or search. Do not weaken this
  restriction in UI-only code or a model prompt.
- A registry entry is not evidence that a clinical workflow is complete. New
  side effects require Runtime permission, durable approval, idempotency and a
  separately reviewed medical workflow.

## Change and test rules

- Add a versioned definition and risk profile together; do not mutate a
  released contract in place.
- Run `tests/test_workflow_registry.py`, relevant chat tests and
  `tests/test_security_evaluation.py` after changes.

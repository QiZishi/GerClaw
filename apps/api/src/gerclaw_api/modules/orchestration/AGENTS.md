# Orchestration Module Instructions

## Responsibility

This module owns durable coordination of an already-defined turn: Trace
idempotency, completed replay, session-lease ownership, cancellation/failure
finalization and PHI-free operational metrics. It does not own prompts, model
calls, medical policy, patient data, tools, Memory, RAG or Skill behaviour.

## Invariants

- A running Trace can be adopted only after the caller owns its session lease.
- A cancellation is visible only after the supplied finalizer durably writes a
  cancelled Trace; a failed finalization must surface an explicit error.
- Completed traces replay only an already persisted assistant response.
- The coordinator never sees user text, document body, image payload, model
  output or clinical data; private replay artifacts stay in the Trace service.
- Do not add a second agent, model call or workflow engine here.

## Change and test rules

- Test completed replay, lease adoption, ordinary failure and cancellation
  finalization whenever lifecycle code changes.
- Re-run chat cancellation, replay, lease and API-contract tests.

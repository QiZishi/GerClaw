# Observability Feedback Module Instructions

## Responsibility

This module owns PHI-free operational projections derived from encrypted Bad
Case records. It helps administrators prioritize reliability work; it is not a
patient-record viewer, a replay system, or an automatic model-training path.

## Invariants

- Accept only pre-aggregated source, severity, status and count metadata.
- Never accept, load, emit or derive output from a trace input, feedback text,
  attachment, image, encrypted snapshot, user identifier or provider payload.
- A Bad Case may enter a synthetic Eval only after an authorised reviewer has
  independently authored a de-identified canonical case; this module never
  promotes a record automatically.

## Change and test rules

- Add deterministic aggregate tests for every new metric.
- Keep administrator APIs tenant-scoped and account-admin protected.
- Run the module tests and the affected administrative API tests.

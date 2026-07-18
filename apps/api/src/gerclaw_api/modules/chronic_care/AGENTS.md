# Chronic Care Module Instructions

## Responsibility

This module owns the caller-scoped ledger for self-reported chronic conditions
and measurements. It provides encrypted persistence and non-clinical numeric
direction only; it is not a diagnosis, triage, goal-setting, reminder,
adherence, medication or treatment engine.

## Invariants

- Conditions are always `self_reported` until a future authorised clinical
  workflow establishes another state. The module must not imply confirmation.
- Condition labels, metric labels, values, units and measured times are PHI and
  encrypted at rest. They never enter Trace payloads, logs, metric labels,
  Qdrant, prompts or public data beyond the authenticated owner projection.
- Measurements are append-only. The server returns `rising`, `falling`,
  `unchanged` or `insufficient_data` by comparing equal-label values; these are
  arithmetic directions, never abnormality, target attainment or risk.
- Every lookup and mutation is tenant- and actor-scoped. A measurement must
  belong to the caller-owned condition selected by its path parameter.
- A named active doctor may receive this ledger only through the consent
  module's current `chronic_care_read` grant. That projection is read-only,
  remains limited to self-reported conditions, measurements and arithmetic
  directions, and must re-check the grant before every read.

## Change and test rules

- Any threshold, target, interpretation, notification, medication action or
  risk-alert source requires a versioned, evidence-traceable, medically
  reviewed rule and its own Runtime/HITL contract.
- Test encrypted persistence, tenant/actor isolation, append-only semantics,
  malformed payloads, non-finite values, ordering and trace redaction.
- Test doctor reads before grant, after grant, after revoke/expiry and across
  tenants. No doctor route may add a measurement, target, interpretation or
  treatment action.

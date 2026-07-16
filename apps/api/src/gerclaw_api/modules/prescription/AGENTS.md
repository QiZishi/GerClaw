# Prescription Intake Module

## Responsibility

This module owns only the versioned, encrypted collection of minimum information for future five-prescription and medication-review workflows. It never generates a prescription, medication action, diagnosis, risk score, or clinical recommendation.

## Invariants

- Fields and requiredness are server-owned immutable definitions; clients submit values only for declared field IDs.
- Every record is scoped by verified `tenant_id + actor_id + session_id`; values are encrypted and may not enter logs, Trace payloads, vector indexes, or model prompts.
- Completed information has the explicit terminal state `information_complete_pending_governance`; it is not a review queue and does not imply doctor approval.
- Medical rules, sources, physician approval, and patient authorization remain required before any clinical output can be enabled.

## Verification

- Contract tests cover extra keys, unknown fields, overlong values, stale revisions and cross-principal access.
- Persistence changes require Alembic upgrade/check and encrypted-column inspection.
- Frontend changes require BFF allowlist, Zod contracts, build and browser evidence.

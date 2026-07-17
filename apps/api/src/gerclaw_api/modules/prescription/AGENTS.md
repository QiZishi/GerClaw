# Prescription Intake Module

## Responsibility

This module owns versioned, encrypted intake plus evidence-bound, structured five-prescription **draft** generation. Medication-review collection has its own `modules/medication_review/` boundary. It never issues an executable prescription, deterministic diagnosis, medication action, or unverified medication-risk conclusion.

## Invariants

- Fields and requiredness are server-owned immutable definitions; clients submit values only for declared field IDs.
- Every record is scoped by verified `tenant_id + actor_id + session_id`; values and uploaded-document references are encrypted and may not enter logs, Trace payloads, vector indexes, or model prompts.
- Start/update operations create an atomic Runtime Trace containing only kind, definition version, answer/document counts, operation and result status. Never add answer text, filenames, document IDs or raw request bodies to that Trace.
- A five-prescription intake may hold up to five active, same-session `UploadedDocument` IDs. MinerU-extracted bodies stay in the document module; the review-draft workflow resolves those IDs again under the same owner/session boundary and labels their count as **uploaded input/provenance**, never as local medical knowledge-base evidence.
- Completed information has the explicit terminal state `information_complete_pending_governance`; it is not doctor approval.
- `prescription-draft` first resolves the complete private input, blocks deterministic red flags, retrieves local evidence, requests strict structured output, and writes server-owned evidence IDs/locators. It always returns `needs_clinician_review` and a fixed disclaimer.
- In the absence of an audited DDI/Beers/dose rule set, the medication section may only organize the existing medication list, monitoring and clinician/pharmacist review questions. It must explicitly say that those rule checks were not executed; it must not suggest starting, stopping, replacing, changing or dosing medication.

## Verification

- Contract tests cover extra keys, unknown fields, overlong values, stale revisions, cross-principal access and uploaded-document ownership.
- Persistence changes require Alembic upgrade/check and encrypted-column inspection.
- Frontend changes require BFF allowlist, Zod contracts, build and browser evidence.

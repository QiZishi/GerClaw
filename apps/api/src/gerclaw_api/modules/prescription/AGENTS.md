# Prescription Intake Module

## Responsibility

This module owns versioned, encrypted intake plus evidence-bound, structured five-prescription **draft** generation. Medication-review collection has its own `modules/medication_review/` boundary. It never issues an executable prescription, deterministic diagnosis, medication action, or unverified medication-risk conclusion.

## Invariants

- Fields and requiredness are server-owned immutable definitions; clients submit values only for declared field IDs.
- Every record is scoped by verified `tenant_id + actor_id + session_id`; values and uploaded-document references are encrypted and may not enter logs, Trace payloads or vector indexes. The resolved MinerU body may enter only this owner/session-bound draft model input as explicitly delimited **untrusted patient input**; it never becomes a knowledge-base citation or system instruction.
- Start/update operations create an atomic Runtime Trace containing only kind, definition version, answer/document counts, operation and result status. Never add answer text, filenames, document IDs or raw request bodies to that Trace.
- A five-prescription intake may hold up to ten active, same-session `UploadedDocument` IDs. MinerU-extracted bodies stay in the document module; the review-draft workflow resolves those IDs again under the same owner/session boundary, within the configured 273,000-character aggregate budget without silent truncation. Each resolved document is an owner-visible **patient-material evidence** source with its own evidence ID and provenance; it is never indexed into, or mislabeled as, local medical knowledge-base evidence.
- Completed information has the explicit terminal state `information_complete_pending_governance`; it is not doctor approval.
- `prescription-draft` first resolves the complete private input, short-circuits deterministic red flags, retrieves local evidence, accepts validated online-search evidence when available, and binds same-session uploaded materials as patient evidence. It requests strict structured output and writes server-owned evidence IDs/locators. It always returns `needs_clinician_review` and a fixed disclaimer.
- The draft route must resolve the server-owned `prescription@1.0.0` workflow risk profile before model execution. The entire workflow has a configurable 600-second default Runtime budget; it is separate from the 180-second per-model-candidate deadline and must fail closed on budget exhaustion.
- When a current medication list is supplied, the server attaches `medication-rules-v2` outside the model output. It is a limited, source-traceable DDI/dose/duplicate/polypharmacy review plus one narrowly qualified Beers-related signal, pending clinical governance; it is never a complete medication review. The model may accurately record a user-provided dose and propose a medication start, stop, replacement or dose change only in an evidence-bound recommendation slot. An unknown evidence ID or affirmative action outside that slot has no attributable evidence: discard that untrusted model projection and return the explicit review-only baseline rather than a late 503. The final report carries one unified risk notice. The model cannot create, override or explain deterministic rule findings.

## Verification

- Contract tests cover extra keys, unknown fields, overlong values, stale revisions, cross-principal access and uploaded-document ownership.
- Persistence changes require Alembic upgrade/check and encrypted-column inspection.
- Frontend changes require BFF allowlist, Zod contracts, build and browser evidence.

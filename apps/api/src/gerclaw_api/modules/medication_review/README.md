# Medication review intake

This module defines the server-owned, non-clinical information collection contract for the future medication-review workflow. Values are stored through the encrypted clinical-intake service. It also exposes an owner-scoped reconciliation preview for complete list rows: after Unicode/whitespace normalization it reports only rows whose text is exactly identical, so a patient and clinician can spot accidental duplicate entry.

The preview is not duplicate-drug detection: it does not infer drug identities, map synonyms or ingredients, parse dosage, or make DDI, Beers, contraindication or dose decisions. Every match is explicitly a candidate for clinician/pharmacist review. `GET /api/v1/clinical-intakes/{id}/medication-reconciliation` is rate-limited, owner-scoped, non-persistent and never writes raw medication text into Trace payloads.

The current contract deliberately does not accept uploaded documents. Five prescription intake has a distinct, owner/session-scoped MinerU document input path; reusing it for medication review would silently expand the evidence boundary before medical rules, patient authorization, and physician approval exist.

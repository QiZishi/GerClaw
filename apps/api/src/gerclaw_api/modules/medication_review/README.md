# Medication review

This module stores medication-review inputs through the encrypted clinical-intake service and provides two separate outputs:

- `GET /api/v1/clinical-intakes/{id}/medication-reconciliation` is a non-clinical preview of only Unicode/whitespace-equivalent list rows.
- `POST /api/v1/clinical-intakes/{id}/medication-review-draft` creates a deterministic, clinician-review-only artifact from the installed source-traceable rule set. It returns risk hits, rule version, source locators, corpus SHA-256 fingerprints, coverage state, and a fixed medical disclaimer. No LLM, RAG, web search, or external medication provider receives the list.

`rules/core-v1.json` currently contains a limited group of statin-related DDI rules and a rosuvastatin daily-dose threshold from the local `冠心病心脏康复基层合理用药指南` corpus file. It also contains one age-qualified benzodiazepine signal from a local insomnia guideline excerpt: it asks the clinician to verify whether the drug is being used for insomnia; a medication list alone never establishes that indication. Each source record carries a locator and the source file SHA-256, so a reviewer can verify the exact corpus version. Results are concrete rule-hit conclusions for clinician/pharmacist review, not a diagnosis or a patient-executable medication decision.

Contraindicated and major findings additionally create an owner-scoped fixed
safety alert in the same database transaction. The alert deliberately omits
drug names, doses, rule text and source locators; it only directs the person to
urgent clinician/pharmacist review and does not authorise self-adjustment.

Beers-related coverage is reported as `limited_source_traceable`, not as a full Beers implementation. The system does not turn a non-match into “no finding” or “safe”; expanding coverage requires a permitted versioned dataset and clinical governance review. Medication-review intake accepts no document references, because five-prescription uploads have a distinct owner/session-scoped MinerU input boundary.

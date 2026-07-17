# Medication Review Module Instructions

## Responsibility

This module owns the versioned, encrypted intake definition, owner-scoped medication-list reconciliation, and deterministic medication-rule review artifact. The installed `rules/core-v1.json` rule set is deliberately limited: it provides only rules with source metadata, a corpus fingerprint, and a precise locator. It produces clinician-review-only risk conclusions, never a diagnosis, prescription, or self-executable medication instruction.

## Invariants

- The server owns immutable fields and requiredness; clients submit values only for declared IDs.
- The present intake accepts no uploaded-document references. A future review workflow must define and validate its own evidence boundary before enabling attachments.
- The reconciliation preview may compare only Unicode/whitespace-normalized complete list rows. It must not normalize synonyms, dosage forms, ingredients or dosing instructions, and every duplicate is labelled as a candidate for human review.
- The rules engine may perform only explicit alias matches declared in the versioned rule artifact. A non-match is incomplete coverage, never a safety conclusion.
- Every DDI/dose finding must carry source IDs resolving to a source title, locator, local corpus path, and SHA-256 fingerprint. Do not embed copyrighted source text in a rule file.
- Beers rules remain `not_installed_no_licensed_source` until a permitted, versioned source and clinical governance approval are supplied. Do not silently convert this state to “no Beers finding”.
- Rule output must say it needs clinician/pharmacist review and must not instruct a patient to start, stop, replace, or independently adjust any medication.
- No medication list, reaction description, identifier, or raw request body may enter logs, Trace payloads, vector indexes, model prompts, or public contracts.
- Any additional rules engine must be versioned, source-traceable, medically reviewed, and governed by Runtime/HITL before it can emit a clinical fact. Update the coverage contract whenever a source is added, removed, or expires.

## Change and test rules

- Update the service state-machine tests whenever fields or attachment rules change.
- Do not add an LLM, RAG, web search, or external medication database to this path without a separately approved plan and medical review. External label feeds must be imported into a reviewed, versioned artifact before they affect a result.

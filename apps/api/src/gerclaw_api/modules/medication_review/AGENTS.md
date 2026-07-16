# Medication Review Module Instructions

## Responsibility

This module owns the versioned, encrypted intake definition for a future governed medication-review workflow. It does not evaluate medicines, infer a diagnosis, calculate a risk score, or recommend stopping, starting, or changing a dose.

## Invariants

- The server owns immutable fields and requiredness; clients submit values only for declared IDs.
- The present intake accepts no uploaded-document references. A future review workflow must define and validate its own evidence boundary before enabling attachments.
- No medication list, reaction description, identifier, or raw request body may enter logs, Trace payloads, vector indexes, model prompts, or public contracts.
- Any future rules engine must be versioned, source-traceable, medically reviewed, and governed by Runtime/HITL before it can emit a clinical fact.

## Change and test rules

- Update the service state-machine tests whenever fields or attachment rules change.
- Do not add an LLM, RAG, web search, external medication database, or clinical output without a separately approved plan and medical review.

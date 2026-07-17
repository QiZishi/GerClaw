# Medication Review Module Instructions

## Responsibility

This module owns the versioned, encrypted intake definition, owner-scoped medication-list reconciliation, and deterministic medication-rule review artifact. The installed `rules/core-v1.json` currently carries the `medication-rules-v3` artifact. It provides only rules with source metadata, a corpus fingerprint, and a precise locator. It produces source-bound clinical review conclusions, never a diagnosis or an unqualified patient-executable medication instruction.

## Invariants

- The server owns immutable fields and requiredness; clients submit values only for declared IDs.
- The present intake accepts no uploaded-document references. A future review workflow must define and validate its own evidence boundary before enabling attachments.
- The reconciliation preview may compare only Unicode/whitespace-normalized complete list rows. It must not normalize synonyms, dosage forms, ingredients or dosing instructions, and every duplicate is labelled as a candidate for human review.
- The rules engine may perform only explicit alias matches declared in the versioned rule artifact. A non-match is incomplete coverage, never a safety conclusion.
- Every DDI/dose finding must carry source IDs resolving to a source title, locator, local corpus path, and SHA-256 fingerprint. Do not embed copyrighted source text in a rule file.
- `medication-rules-v3` includes a limited group of exact drug-pair and daily-dose rules from four source-traceable local corpora, plus one age-qualified benzodiazepine signal that still requires verification of insomnia indication. Coverage is `limited_source_traceable`, not a complete DDI, dose or Beers screen; do not convert a non-match into “safe” or “no Beers finding”.
- Rule output may state a source-bound clinical conclusion and concrete clinician-review action. It must not fabricate evidence, disguise incomplete coverage as safety, or issue an unqualified patient-executable medication instruction. The patient-facing risk notice appears once at the end.
- A `contraindicated` or `major` deterministic hit also creates an owner-scoped
  fixed safety alert in the same transaction. That alert must not include a
  medication name, dose, rule text, source locator or raw intake content; it
  asks for urgent clinician/pharmacist review and never authorises self-change.
- No medication list, reaction description, identifier, or raw request body may enter logs, Trace payloads, vector indexes, model prompts, or public contracts.
- Any additional rules engine must be versioned, source-traceable, medically reviewed, and governed by Runtime/HITL before it can emit a clinical fact. Update the coverage contract whenever a source is added, removed, or expires.

## Change and test rules

- Update the service state-machine tests whenever fields or attachment rules change.
- Do not add an LLM, RAG, web search, or external medication database to this path without a separately approved plan and medical review. External label feeds must be imported into a reviewed, versioned artifact before they affect a result.

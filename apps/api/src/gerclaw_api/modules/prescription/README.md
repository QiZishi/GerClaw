# Prescription & Medication Intake

This is a fail-closed intake module for the future governed five-prescription and medication-review workflows. It stores only caller-provided, minimum discussion context in an encrypted record. It does not call an LLM, RAG, web search, rules engine or clinical tool.

For the five-prescription intake, the caller may attach up to five already parsed, active documents from the same conversation. The intake stores only encrypted document IDs; the MinerU-extracted text remains in the private document store. A later medically governed report may resolve those IDs into its input template and display them as “上传资料依据” for traceability. They are never indexed into the public/local knowledge base and never satisfy the medical-evidence requirement on their own.

## State

- `collecting`: required server-defined fields are still absent.
- `information_complete_pending_governance`: required fields are present, but medical rules, patient authorization and physician-review workflow are not enabled. No clinical output exists in this state.

## Boundaries

The module depends on its repository and encrypted database model only. Routes verify identity, session ownership and rate limits. The Runtime Harness and later approved clinical workflow may consume a validated snapshot only after the missing medical governance requirements are implemented.

Write operations also emit an atomic, PHI-free Runtime Trace. The trace contains only the intake kind, definition version, answer/document counts, operation and result status; it never stores answer text, filenames or uploaded-document identifiers.

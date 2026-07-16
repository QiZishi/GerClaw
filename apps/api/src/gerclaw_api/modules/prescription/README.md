# Prescription & Medication Intake

This is a fail-closed intake module for the future governed five-prescription and medication-review workflows. It stores only caller-provided, minimum discussion context in an encrypted record. It does not call an LLM, RAG, web search, rules engine or clinical tool.

## State

- `collecting`: required server-defined fields are still absent.
- `information_complete_pending_governance`: required fields are present, but medical rules, patient authorization and physician-review workflow are not enabled. No clinical output exists in this state.

## Boundaries

The module depends on its repository and encrypted database model only. Routes verify identity, session ownership and rate limits. The Runtime Harness and later approved clinical workflow may consume a validated snapshot only after the missing medical governance requirements are implemented.

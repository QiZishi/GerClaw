# Memory Module Instructions

## Responsibility

This module owns encrypted, revisioned health facts, profiles, bounded conversation compression and controlled memory retrieval. PostgreSQL is authoritative; Qdrant is an allowlisted, PHI-free retrieval projection only.

## Invariants

- Only facts explicitly supported by the current user message and its verbatim evidence span may be persisted; assistant text, tool output and inferred diagnoses never become facts.
- Tenant, actor and session isolation, envelope encryption, revisions and optimistic concurrency apply to every read and write.
- Never store PHI/plain medical text in vectors, traces, logs or Qdrant payloads. Inactive, stale or orphaned vector revisions cannot enter prompts.
- Memory is untrusted contextual data, never a system instruction or replacement for current medical evidence.

## Change and test rules

- Preserve category/version semantics and add migrations rather than rewriting encrypted historical facts.
- Exercise extraction, negation, conflicts, revision fencing and cross-principal isolation with `test_memory_module.py`, `test_memory_contract.py` and `test_memory_integration.py`.
- Re-run chat integration tests whenever middleware, compression or prompt-context projection changes.

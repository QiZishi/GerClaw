# Privacy Redaction Module

## Responsibility

This module owns versioned, purpose-bound redaction decisions before PHI or
identifiers can leave GerClaw. Its production consumers are external web search
and FastAPI MiMo TTS. It returns a safe text projection and bounded category counts, never
the raw input, matched span, replacement position or a reversible mapping.

## Invariants

- The policy version, patterns and replacement tokens are server-owned. A
  semantic policy change requires a new version and regression canaries.
- No caller may mark an outbound request as redacted without passing through a
  purpose-specific policy function. Fail closed on oversized or blank results.
- Findings are PHI-free category counts only. They are allowed for an internal
  audit decision; source text and matches are forbidden in Trace, metrics,
  logs, Qdrant and provider requests.
- This module classifies and redacts; it does not authorize egress, persist
  mappings, send network requests or make clinical decisions.

## Verification

- Test Chinese/English names, phone numbers, IDs, email, credentials, control
  characters, empty/oversized inputs, absence of source values in findings and
  the actual provider payload of every consumer.
- Re-run each egress consumer's contract test when a policy changes.

# Evolution Signal Instructions

Owns metadata-only online signals for isolated offline evolution. Production requests may
append signals but may never mutate Prompt, Memory, Skill, routing, planning, configuration,
code, or model weights.

Do not include user text, assistant text, retrieved text, filenames, contacts, identifiers,
credentials, or raw provider payloads. Fingerprints must be one-way and non-reversible.
Feedback is the reconciled current value plus revision, not an append-only click counter.

Run privacy, feedback reconciliation, schema, and export allowlist tests after changes.

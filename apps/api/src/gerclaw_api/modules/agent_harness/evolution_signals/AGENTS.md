# Evolution Signal Instructions

Owns metadata-only online signals for isolated offline evolution. This signal sink may never
mutate Prompt, Memory, Skill, routing, planning, configuration, code, or model weights.
That restriction does not disable ordinary actor-owned Memory CRUD or separately governed
low-risk Skill versioning.

Do not include user text, assistant text, retrieved text, filenames, contacts, identifiers,
credentials, or raw provider payloads. Fingerprints must be one-way and non-reversible.
Feedback is the reconciled current value plus revision, not an append-only click counter.

Run privacy, feedback reconciliation, schema, and export allowlist tests after changes.

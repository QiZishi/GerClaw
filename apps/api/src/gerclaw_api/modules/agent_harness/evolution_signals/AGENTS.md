# Evolution Signal Instructions

Owns metadata-only online signals for isolated offline evolution. This signal sink may never
mutate Prompt, Memory, Skill, routing, planning, configuration, code, or model weights.
That restriction does not disable ordinary actor-owned Memory CRUD or separately governed
low-risk Skill versioning.

Do not include user text, assistant text, retrieved text, filenames, contacts, principal or
database identifiers, credentials, or raw provider payloads. Capability IDs must come from
the server manifest; user-created Skill IDs must be purpose-separated keyed HMAC pseudonyms
before persistence or export. Fingerprints must be purpose-specific keyed HMAC values and
non-reversible.
Feedback is the reconciled current value plus revision, not an append-only click counter.
Collection is post-commit and best-effort: it may not change a Run, cancellation, recovery,
or feedback result, and request paths may not await it. Reconciliation must be monotonic in
both occurrence time and feedback revision. Export is bounded, deterministic, and validates
every row against the public allowlist contract.

Run privacy, feedback reconciliation, schema, and export allowlist tests after changes.

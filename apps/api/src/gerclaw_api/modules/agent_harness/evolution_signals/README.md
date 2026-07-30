# Evolution Signals

Current implementation defines a strict, content-free `EvolutionSignal` contract and an
online metadata collector. It reconciles one current row per Run after the authoritative
Run/Trace transaction commits, and refreshes that row after accepted feedback changes.
Collector work is scheduled into an injected timeout-, queue-, and concurrency-bounded
background set; request paths never await it. The low concurrency gate prevents telemetry
from occupying the shared business database pool. Failure, timeout, queue saturation, or
collector-task cancellation is deliberately non-fatal to chat, cancellation, recovery, and
feedback.
Production images do not gain optimizers or training dependencies.

Unknown fields fail validation to prevent accidental content leakage. Stage 6 adds the
isolated official-optimizer evaluation workflow. A bounded keyset-paginated JSONL exporter
emits exactly the validated signal schema; it never emits database Run, tenant, actor,
conversation, Trace, message, or provider fields. Run fingerprints use a purpose-specific
HMAC key configured by `GERCLAW_EVOLUTION_SIGNAL_HMAC_KEY`; production must provide it
explicitly. User-created Skill IDs are also purpose-separated HMAC pseudonyms, while
capability IDs must match the server-owned manifest allowlist. Monotonic upsert conditions
prevent a late Run-status or feedback collector from rolling back a newer signal. Measure
success with privacy allowlist tests, revision-correct feedback, complete lineage, and zero
production mutations.
Trace error codes must exactly match the shared server-owned Chat error allowlist; an unknown
or content-bearing value is projected to the generic failed/cancelled code.
“Zero production mutations” applies to this signal pipeline, not to ordinary actor-owned
Memory CRUD or separately governed low-risk Skill content versions.

Consumers: Chat completion/failure/cancellation, startup orphan-Run interruption, feedback
reconciliation, and the isolated offline evaluator. Configuration is injected by the
application; this package reads no environment. Failure semantics: a legacy or invalid
persisted Run plan degrades safely to empty Skill/capability IDs without interpreting its
free-form payload while preserving outcome metadata; other signal failures leave
user-facing production behavior unchanged. Known limits: failed provider attempts without
validated token counters contribute zero, and no optimizer runs in the request path.
`risk_level` is only a deterministic routing-risk proxy; offline consumers must not treat
it as a clinical risk score. HMAC key rotation currently starts a new fingerprint epoch
rather than rekeying existing rows. Empty Skill/capability IDs do not yet distinguish a
genuinely empty plan from legacy-plan degradation. Acceptance: content-field negative
tests, one-way fingerprints, reconciled feedback revisions, bounded deterministic export,
migration upgrade/downgrade, and no online control-plane mutation.

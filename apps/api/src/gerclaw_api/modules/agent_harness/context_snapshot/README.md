# Context Snapshot

This package owns the versioned, immutable `AgentContext`, bounded conversation-history
models, `ProductionContextSnapshotAssembler`, encrypted persistence contracts, and uploaded
input projector. The composition entry consumes the assembler through `HarnessComponents`;
`ProductionAgentHarness`, `ChatService`, and `RunResumeService` are the consumers.

Validation forbids unknown fields and caps every collection/text field. A validation failure
stops the turn before model construction.

`PersistedContextSnapshot` freezes the model-visible history, Profile projection and version,
Memory references, session summary, ClinicalState, exact validated Skill definitions, and
already parsed owner-scoped documents. `PersistedRunPlan` freezes route, dynamic DAG,
SAVI/C3 decision, selected capabilities and reusable results, workflow policy, Harness config,
execution budget, attachments, and regeneration identity. `FrozenRunState` cross-validates
both contracts.

New turns assemble these contracts once and save them in the encrypted
`AgentRun.context_snapshot` and `AgentRun.plan` columns. Explicit resume reconstructs the
request from the owner-scoped Message and Trace, validates tenant/actor/session/trace/input
identity, restores images from encrypted Trace artifacts with SHA-256 checks, and then passes
the frozen state to Chat. Chat does not create another user Message or reload mutable
history/Profile/Memory/Skill/document inputs.

Failure semantics:

- Unknown fields, unsupported schema versions, count/identifier drift, corrupt fingerprints,
  cross-actor identity, or route/plan mismatch fail closed as invalid resume material.
- Legacy interrupted Runs without `context-snapshot-v1`/`run-plan-v1` are intentionally not
  reconstructed from current mutable state.
- Authorization and service availability are checked at resume time; the snapshot never
  grants permissions.

Known limit: the snapshot freezes inputs and completed owner-capability results, but the
current executor does not yet persist every AgentScope tool-call checkpoint. A resumed
unfinished model/tool node may execute again behind existing idempotency and fencing
boundaries. Node-level checkpoint continuation remains a Run Lifecycle responsibility.

Measure improvement with byte-stable serialized snapshots across resume, zero mutable
context fetches on the resume path, bounded input, no cross-actor references, uninterrupted
Run/Event identity, and recovery integration tests. Acceptance requires context, Harness,
Chat, Run Resume, and real PostgreSQL/Redis recovery tests to pass.

# Context Snapshot

This package owns the versioned `AgentContext` and bounded conversation-history models.
The existing Harness assembler remains the current producer; `ProductionAgentHarness` is
the consumer.

Validation forbids unknown fields and caps every collection/text field. A validation failure
must stop the turn before model construction. Compression, answer-version selection, and
persisted snapshots arrive in stage 2/3.

Measure improvement with deterministic serialized snapshots, bounded token input, no
cross-actor references, and unchanged Harness context tests.

Consumers: `ProductionAgentHarness` and future run persistence. Configuration: caps remain
schema-owned; token budgets arrive through `ResolvedHarnessConfig`. The upload projector
accepts only owner-validated Document/Image models. Known limit: snapshots are not persisted
or compressed yet. Acceptance: compatibility imports and Harness regressions remain green.

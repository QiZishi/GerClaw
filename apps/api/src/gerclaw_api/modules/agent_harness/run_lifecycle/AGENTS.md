# Run Lifecycle Instructions

Owns typed Harness failures and public-stream normalization. It does not own database
transactions, leases, traces, conversations, or SSE transport.

Trust boundary: accept only already validated text and evidence-presence callbacks.
Never expose provider payloads, credentials, private reasoning, or partial unsafe medical
sentences. An attempt is private until the owning boundary validates it and the persistence
owner wins both worker fencing and current-attempt CAS. Never allocate a public sequence,
update AnswerVersion/Memory/Context/Artifact, or invoke user-facing SSE/TTS/copy/export from a
staging, rejected, or invalidated attempt. Preserve a single public terminal outcome and
cancellation idempotency.

The validated attempt must pass through the deterministic `PublicAnswerProjection` before
promotion. It may remove clearly generic terminal boilerplate and normalize layout, but must
not call another model, rewrite clinical meaning, remove citations, remove situation-specific
risk actions, or add internal safety explanations. The one canonical medical disclaimer is
owned by the Harness after projection.

Claim-evidence failure is localized: reopen the pre-model checkpoint once with bounded private
feedback, then deterministically remove only clinical segments that remain unbound. Never turn
one unsupported sentence into a failed Run when other valid answer content remains, and never
publish the rejected sentence or the repair process.

`public_operation_id` is stable across repair attempts. Attempt numbers are monotonic.
`ValidationFeedback` must contain only bounded error metadata and checkpoint/contract
identifiers—never user text, provider payload, hidden prompts, credentials, sealed cases, or
private reasoning. Cancellation, interruption, and immediate steer invalidate uncommitted
attempts; resume starts after the latest committed checkpoint.

Every persisted `PlanNode` transition must be validated against the exact frozen
`DynamicPlan`, protected by the current worker fencing token, and committed atomically with
the encrypted `plan-execution-v1` snapshot plus a content-free append-only audit row. Never
advance a plan for a non-running Run or accept a replayed/multi-node transition that did not
come from the declared optional-skip operation. A legacy plan without an execution snapshot
restores as all-pending; new Runs must persist the initial snapshot explicitly.

Execution-time user instructions use the encrypted `RunDirective` ledger. Conversation
sequence allocation is monotonic; idempotency is actor-scoped. A worker may consume a queued
instruction only after a fencing-protected claim at a named safe boundary, and may mark it
applied only with the same fence and boundary identity. A newer fence may adopt a stale claim;
the old worker must then fail. `interrupt_and_steer` must never be consumed by the original
Run and becomes claimable only after it is bound to a controlled successor. An instruction
that races with a true terminal Run remains `pending_next_run`, never silently disappears.
`pending_next_run` must be bound to the next non-resume actor-owned Run. Terminal deferral and
successor creation must serialize on the Conversation row so either commit order produces one
consumable successor binding; a parking state with no production consumer is forbidden.
Claim a boundary batch before injection, preflight the complete batch, and apply it atomically;
no prefix may become `applied` when a later item fails admission. Respect both the configured
per-boundary burst limit and the independent per-Run restoration limit. An applied directive
must have an idempotent Conversation user-message projection. Medical directive text enters
the next mutable ClinicalState only through the deterministic user projector with directive
provenance and `reported` status; it must never become a model-inferred confirmed fact.
Queued red flags must short-circuit before the next model call. Never expose idempotency keys,
worker fencing tokens, or private safe-boundary identifiers in public DTOs.

AgentScope model admission must run at its actual `compress_context` entry, before the
Provider side effect and before `ModelCallStartEvent`. Tool capacity admission is one atomic
decision over the complete AgentScope sequential/concurrent batch before any owner call.
The hard gate must count AgentScope's actual prepared messages and activated tool schemas;
counter failure falls back to a complete content-block projection rather than failing the Run.
Capacity rejection must be returned through the governed tool failure path so the Agent can
repair the failed step privately; it must not turn a recoverable tool mistake into a public
Run failure. Apply queued directives after the entire outstanding tool round completes, never
between concurrently running members.

Inputs are bounded text deltas and validated lifecycle commands; outputs are safe public
text fragments or stable typed errors. Do not import concrete Runtime, Memory, RAG, Search,
Skill, Workflow, or persistence implementations.

Run `tests/test_agent_harness.py`, `tests/test_agent_harness_safety.py`,
`tests/test_agent_run_service.py`, `tests/test_chat_service.py`, and
`tests/test_chat_cancellation.py` after changes. Directive changes also require
`tests/test_run_directive_service.py`, `tests/test_runtime_directive_coordinator.py`, and
`tests/test_run_directive_integration.py`; boundary injection changes require the
queued-directive cases in `tests/test_agent_harness.py` and `tests/test_chat_service.py`.
Plan checkpoint persistence also requires `tests/test_run_recovery_integration.py`. When
persistence changes, run Alembic upgrade, downgrade, re-upgrade, and `alembic check` against
PostgreSQL.

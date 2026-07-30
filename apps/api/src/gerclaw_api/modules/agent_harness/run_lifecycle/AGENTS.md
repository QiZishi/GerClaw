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

`public_operation_id` is stable across repair attempts. Attempt numbers are monotonic.
`ValidationFeedback` must contain only bounded error metadata and checkpoint/contract
identifiers—never user text, provider payload, hidden prompts, credentials, sealed cases, or
private reasoning. Cancellation, interruption, and immediate steer invalidate uncommitted
attempts; resume starts after the latest committed checkpoint.

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

Inputs are bounded text deltas and validated lifecycle commands; outputs are safe public
text fragments or stable typed errors. Do not import concrete Runtime, Memory, RAG, Search,
Skill, Workflow, or persistence implementations.

Run `tests/test_agent_harness.py`, `tests/test_agent_harness_safety.py`,
`tests/test_agent_run_service.py`, `tests/test_chat_service.py`, and
`tests/test_chat_cancellation.py` after changes. Directive changes also require
`tests/test_run_directive_service.py`, `tests/test_runtime_directive_coordinator.py`, and
`tests/test_run_directive_integration.py`; boundary injection changes require the
queued-directive cases in `tests/test_agent_harness.py` and `tests/test_chat_service.py`.
When persistence changes, also run Alembic upgrade, downgrade, re-upgrade, and `alembic check`
against PostgreSQL.

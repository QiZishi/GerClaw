# Run Lifecycle

Current implementation contains the existing sentence safety buffer, canonical text stream,
wall-clock stream guard, stable Harness errors, and a Protocol-driven AgentScope event
projector extracted without behavior changes. The root `harness.py` is a small compatibility
facade; the composition entry remains outside this package and injects budgets, approvals,
evidence state, Memory failure checks, and timeout error construction.

Unsafe or empty output raises a typed, repairable error; trailing whitespace is never
published as a new semantic delta. A chat answer now executes inside an encrypted private
`AgentRunAttempt`. Validated stream events remain unsequenced and invisible to SSE/replay until
the answer, `AnswerVersion`, and terminal Run transition can commit together. The successful
attempt is then selected through a fencing-protected compare-and-swap and its events receive
public sequences in one transaction. Rejected and invalidated attempts retain only private,
bounded audit lineage and never become Conversation, Memory, Context, TTS, Artifact, copy, or
export input.

The stable public slot is `public_operation_id`; retry attempts use a monotonic number but keep
that operation ID. `ValidationFeedback` is versioned, content-free metadata bound to the exact
step and pre-step checkpoint. Terminal failure, cancellation, or interruption invalidates every
uncommitted attempt. Persistence, replay sequence, recovery, fencing, and the versioned
`AgentRun` state machine remain owned by the chat/session layer.

Execution-time requirements now have an encrypted `RunDirective` fact source with
actor-scoped idempotency and a conversation-scoped monotonic sequence. Queued requirements use
`pending → claimed → applied`; claim and apply are bound to the same worker fencing token and
safe-boundary ID. Worker adoption can reclaim only a lower-fence claim, while the previous
worker is rejected. Users may withdraw only unclaimed directives. An instruction created after
the target Run reaches a true terminal status becomes `pending_next_run`. Immediate steering
requirements are intentionally excluded from the original Run's claim query and become
consumable only after the orchestration layer binds a controlled successor Run.

`interrupted` is a recoverable execution boundary, not a terminal outcome. It records
`interrupted_at`, closes the current public event stream, rejects worker events until a fenced
resume, and may transition to `running` or `cancelled`. Only `completed`,
`completed_with_warnings`, `failed`, and `cancelled` set `completed_at`; those true terminal
states have no outgoing transitions. A resumed Run retains its last interruption timestamp for
audit while a new fencing token prevents the old worker from writing.

The directive ledger is currently an internal persistence boundary. Public API fan-out,
successor creation, per-model/tool boundary polling, Context reserve injection, and Composer
status projection are the next change set; no UI or API claims immediate steering works before
those consumers are connected.

Measure improvement with one terminal event, no failed-attempt bytes in SSE/replay, atomic
AnswerVersion/current-attempt selection, stale-fence/CAS rejection, cancellation tests, and
byte-equivalent safe text in Harness regression cases. Current limitation: the chat answer is
the smallest promoted unit, so validated deltas are released as a burst after durable success;
future node-local checkpoints may promote smaller independently valid sections without exposing
later failed work.

Consumers: the composition entry and chat/session services through the
`ProductionAgentHarness` facade. Configuration:
output, iteration, Context ratio, timeout, and approval limits arrive through
`ResolvedHarnessConfig`; these primitives read no environment and import no concrete Runtime,
Memory, RAG, Search, Skill, Workflow, or persistence owner. The chat/session layer persists
`AgentRun`/`RunEvent`; this package owns only the deterministic transition contract.
Acceptance: a facade under 100 lines, stable error types, dependency-boundary tests, canonical
text fixtures, migration upgrade/downgrade/check, private-attempt projection tests, and
SSE/cancellation regressions that prove partial failure is never public.

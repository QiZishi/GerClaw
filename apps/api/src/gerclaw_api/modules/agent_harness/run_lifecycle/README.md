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

`AgentRun.plan` now carries an encrypted `plan-execution-v1` snapshot bound to the canonical
full `DynamicPlan`. New Runs persist the all-pending snapshot; legacy rows without it recover
as all-pending without rewriting their frozen payload. The persistence owner locks the
actor-scoped Run, verifies `running` plus the exact fencing token, validates the proposed
single-node transition, and atomically updates the snapshot/revision with a content-free
append-only `agent_run_plan_node_events` record. Declared multi-node optional skips expand to
one audit record per node in the same transaction. Stale fences, repeated snapshots,
dependency bypasses, and non-running Runs cannot advance the plan. This change establishes
the durable checkpoint fact source. The production Harness now observes every checkpoint
before its attachment, evidence, answer-model, emergency, or clarification side effect and
persists completion only after success. Skill and already-returned governed-capability results
persist their optional-node completion after result validation. A stale fence or persistence
failure therefore stops the next governed Harness side effect. Owner capabilities now enter
`running` only after the Run exists; their validated result and `completed` transition persist
atomically. An optional owner failure remains private, preserves the valid answer, and produces
`completed_with_warnings` rather than a false full failure. Stable node failures are not added
to the public answer. Entering `interrupted` now normalizes every durably `running`
PlanNode to `failed/RUN_INTERRUPTED_BEFORE_NODE_COMMIT` in the same transaction as the
Run status change. The node keeps its attempt number and append-only audit lineage; an
adopted worker receives a higher fence and may reopen that exact capability as the next
attempt. Completed, pending, skipped, and already-failed nodes are not changed by this
normalization. Durable output reuse for non-owner nodes remains separate recovery work
rather than being implied here.

Queued requirements are available through the owner-scoped Trace create API and Run list/delete
APIs. The Trace lookup closes the period before a successful stream reveals a Run ID. The
production Harness checks before the initial model call and immediately after each completed
tool result. Every boundary claims an ordered batch, preflights the complete batch, and only
then marks the whole batch applied in one Run-locked transaction. A configurable per-boundary
limit controls burst size and an independent per-Run limit is the restoration fact source;
the latter does not guess from ReAct iteration counts. A completed, failed, or cancelled Run
moves both pending and in-flight claimed instructions to `pending_next_run` in the same
terminal transaction; a terminal Run cannot accept a late apply.
`pending_next_run` is not a parking-only status: creation of the next non-resume Run binds all
actor-owned deferred directives for that Conversation before the Run commit. Terminal
deferral and successor creation serialize on the Conversation row. If successor creation wins,
the terminal side binds to the active successor; if terminal deferral wins, the successor side
binds the deferred rows. This closes the two-transaction race without polling or duplicate
application.

Applying a directive also creates an idempotent encrypted Conversation user-message projection
in the same transaction. The next non-resume Run projects recent medical directives through
the same deterministic `UserMessageClinicalProjector`, retaining `message:<directive-id>`
provenance and `reported` status; non-medical execution constraints remain Conversation
context rather than clinical facts. A queued deterministic red flag short-circuits before the
next model call. Public directive responses omit idempotency keys, worker fencing tokens, and
private boundary identities. A short configured Trace lookup wait covers the race between SSE
startup and durable Run creation without allowing cross-actor discovery.

Immediate steering now has a distinct durable cross-replica control signal. It never reuses
explicit cancellation: an interrupted worker rejects its private attempt, transitions the Run
to `interrupted`, leaves its Trace out of failed/cancelled terminal projection, and emits a
distinct control-only SSE frame. The normal chat route supplies independent cancel and steer
probes, so either intent still fences final answer promotion even if a provider consumes task
cancellation during cleanup. The coordinator carries the already-persisted steer outcome to
SSE as a typed interruption instead of re-reading mutable Redis state during cleanup. Explicit
cancel takes precedence when both durable signals exist before that outcome is frozen, and
the local merge is monotonic so a stale Redis steer read cannot downgrade a concurrent cancel.
If a provider wrapper converts the injected cancellation into a stream error, the coordinator
reconciles that error with the durable identity-scoped intent before assigning a terminal
outcome. Because a provider cleanup layer may swallow one Python task cancellation while
leaving the task's cancelling counter set, the registry redelivers the same intent on a bounded
schedule. The coordinator synchronously acknowledges the first observed cancellation before
starting database cleanup, which stops redelivery from interrupting the durable terminal
transition. The separately configured `agent_steer_interruption_wait_seconds` remains a bounded
coordination fallback; it does not enlarge the short Trace-to-Run discovery wait.

Answer text is also checked for provider/tool protocol markup before its private attempt can be
promoted. A matching attempt is rejected with content-free `ValidationFeedback`, the stable
pre-model checkpoint is reopened once within the existing retry/model/Token budgets, and the
model receives the concrete format defect privately. Events from the rejected attempt never
receive public sequence numbers; only the replacement attempt is replayable. A second contract
failure ends normally through the typed failure path instead of exposing or concatenating the
invalid fragment.

The immediate-steer API now waits for the old Run's durable `interrupted` state before opening
a deterministic successor Trace. A pending steer reserves the source against ordinary resume;
after binding, the source disappears from recoverable-run lookup. The successor reuses the
encrypted frozen history, Profile/Memory projection, Skill definitions, documents, resolved
configuration, and completed capability results, while recomputing route, ClinicalState,
clinical action, Context budget, and DAG for the new instruction. It does not re-read mutable
Memory or Skill state. Binding and applying the steer uses the successor fence and its already
stored input message, so Conversation history contains the instruction exactly once. Pending
or stale-claimed queue directives move to the successor and lose the old claim. A stable
directive-derived Trace makes completed retries replay the same answer without creating a
third Run. Concurrent retries of the same directive wait for that Trace to become replayable
instead of surfacing a session-busy error; Trace reads refresh the database fact instead of
reusing an identity-map copy of `running`. Queue instructions that race after binding are
atomically redirected to the bound successor while it is running; creation locks that
successor against its terminal deferral, so a concurrent or already-finished successor leaves
the instruction as `pending_next_run` instead of stranding it. Binding transfers the full
consumable set without a smaller hard-coded batch ceiling. The old worker's private attempt remains
invisible, and the successor's first public stage is `已按新要求调整执行`.

Every ReAct model call, including the first, and every permitted tool execution now has a
pre-side-effect capacity boundary. A queued
directive that arrives after the previous tool-result boundary is claimed again immediately
before the next model call, while a model call already in flight remains immutable. Tool
execution is checked after Runtime returns `ALLOW` but before owner invocation, using complete
validated arguments and the effective result ceiling. If remaining model/Token capacity cannot
hold both the bounded result and required follow-up model call, the owner remains untouched and
AgentScope receives bounded private failure feedback so it can answer from already available
context. `DENY` and `ASK` retain their Runtime semantics and are not preempted by this capacity
gate. Persistent plan-node checkpoints and node-local Context recompression remain the next
change set.

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

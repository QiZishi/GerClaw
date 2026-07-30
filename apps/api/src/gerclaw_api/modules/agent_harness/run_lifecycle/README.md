# Run Lifecycle

Current implementation contains the existing sentence safety buffer, canonical text stream,
wall-clock stream guard, stable Harness errors, and a Protocol-driven AgentScope event
projector extracted without behavior changes. The root `harness.py` is a small compatibility
facade; the composition entry remains outside this package and injects budgets, approvals,
evidence state, Memory failure checks, and timeout error construction.

Failures are fail-closed: unsafe or empty output raises a typed error; trailing whitespace
is never published as a new semantic delta. Persistence, replay sequence, recovery, fencing,
and the versioned `AgentRun` state machine remain owned by the chat/session layer.

`interrupted` is a recoverable execution boundary, not a terminal outcome. It records
`interrupted_at`, closes the current public event stream, rejects worker events until a fenced
resume, and may transition to `running` or `cancelled`. Only `completed`,
`completed_with_warnings`, `failed`, and `cancelled` set `completed_at`; those true terminal
states have no outgoing transitions. A resumed Run retains its last interruption timestamp for
audit while a new fencing token prevents the old worker from writing.

Measure improvement with unchanged SSE ordering, one terminal event, cancellation tests,
and byte-equivalent safe text in Harness regression cases.

Consumers: the composition entry and chat/session services through the
`ProductionAgentHarness` facade. Configuration:
output, iteration, Context ratio, timeout, and approval limits arrive through
`ResolvedHarnessConfig`; these primitives read no environment and import no concrete Runtime,
Memory, RAG, Search, Skill, Workflow, or persistence owner. The chat/session layer persists
`AgentRun`/`RunEvent`; this package owns only the deterministic transition contract.
Acceptance: a facade under 100 lines, stable error types, dependency-boundary tests, canonical
text fixtures, and unchanged SSE/cancellation regressions.

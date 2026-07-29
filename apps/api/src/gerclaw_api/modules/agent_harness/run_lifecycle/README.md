# Run Lifecycle

Current implementation contains the existing sentence safety buffer, canonical text stream,
wall-clock stream guard, stable Harness errors, and a Protocol-driven AgentScope event
projector extracted without behavior changes. The root `harness.py` is a small compatibility
facade; the composition entry remains outside this package and injects budgets, approvals,
evidence state, Memory failure checks, and timeout error construction.

Failures are fail-closed: unsafe or empty output raises a typed error; trailing whitespace
is never published as a new semantic delta. Persistence, replay sequence, recovery, fencing,
and the versioned `AgentRun` state machine remain owned by the chat/session layer until
stage 2.

Measure improvement with unchanged SSE ordering, one terminal event, cancellation tests,
and byte-equivalent safe text in Harness regression cases.

Consumers: the composition entry and chat/session services through the
`ProductionAgentHarness` facade. Configuration:
output, iteration, Context ratio, timeout, and approval limits arrive through
`ResolvedHarnessConfig`; these primitives read no environment and import no concrete Runtime,
Memory, RAG, Search, Skill, Workflow, or persistence owner. Known limit: this package does not
yet persist `AgentRun`/`RunEvent`. Stage 2 will add state transitions and replay/recovery.
Acceptance: a facade under 100 lines, stable error types, dependency-boundary tests, canonical
text fixtures, and unchanged SSE/cancellation regressions.

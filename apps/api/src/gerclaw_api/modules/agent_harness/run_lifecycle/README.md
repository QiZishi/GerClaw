# Run Lifecycle

Current implementation contains the existing sentence safety buffer, canonical text stream,
wall-clock stream guard, stable Harness errors, and production one-turn executor extracted
without behavior changes. The root `harness.py` is now a small compatibility facade; the
executor composes injected model/RAG/Memory Protocols and the neighboring component adapters.

Failures are fail-closed: unsafe or empty output raises a typed error; trailing whitespace
is never published as a new semantic delta. Persistence, replay sequence, recovery, fencing,
and the versioned `AgentRun` state machine remain owned by the chat/session layer until
stage 2.

Measure improvement with unchanged SSE ordering, one terminal event, cancellation tests,
and byte-equivalent safe text in Harness regression cases.

Consumers: chat/session services through the `ProductionAgentHarness` facade. Configuration:
output, iteration, Context ratio, timeout, and approval limits arrive through
`ResolvedHarnessConfig`; these primitives read no environment. Known limit: the one-turn
executor remains large and this package does not yet persist `AgentRun`/`RunEvent`. Stage 2
will split state transitions and add replay/recovery. Acceptance: a facade under 100 lines,
stable error types, canonical text fixtures, and unchanged SSE/cancellation regressions.

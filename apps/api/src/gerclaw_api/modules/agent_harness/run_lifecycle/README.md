# Run Lifecycle

Current implementation contains the existing sentence safety buffer, canonical text stream,
and stable Harness errors extracted without behavior changes. `ProductionAgentHarness` is
the current consumer.

Failures are fail-closed: unsafe or empty output raises a typed error; trailing whitespace
is never published as a new semantic delta. Persistence, replay sequence, recovery, fencing,
and the versioned `AgentRun` state machine remain owned by the chat/session layer until
stage 2.

Measure improvement with unchanged SSE ordering, one terminal event, cancellation tests,
and byte-equivalent safe text in Harness regression cases.

Consumer: `ProductionAgentHarness`. Configuration: output and iteration limits arrive through
the facade's resolved config; these primitives read no environment. Known limit: this package
does not yet persist `AgentRun`/`RunEvent`. Stage 2 adds replay/recovery. Acceptance: stable
error types, canonical text fixtures, and unchanged SSE/cancellation regressions.

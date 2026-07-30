# Planning Instructions

Owns bounded dynamic DAG contracts and dependency validation. It does not execute nodes,
resolve permissions, or persist run state.

Plans may use only registered capability IDs and injected budgets. Public summaries must
be safe to show to users and cannot contain prompts, provider payloads, credentials, or
private reasoning. Cycles, unknown references, and self-dependencies must fail closed.
Dependency and fallback references form one acyclic recovery graph. Execution snapshots
contain only node status, bounded attempt counts, stable error codes, and the declared
fallback actually used; restoring a snapshot with different node identities must fail.

Run plan contract, Runtime budget, workflow registry, and Harness tests after changes.

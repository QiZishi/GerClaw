# Planning Instructions

Owns bounded dynamic DAG contracts and dependency validation. It does not execute nodes,
resolve permissions, or persist run state.

Plans may use only registered capability IDs and injected budgets. Public summaries must
be safe to show to users and cannot contain prompts, provider payloads, credentials, or
private reasoning. Cycles, unknown references, and self-dependencies must fail closed.
Dependency and fallback references form one acyclic recovery graph. Execution snapshots
contain only node status, bounded attempt counts, stable error codes, and the declared
fallbacks actually used. Bind a snapshot to the canonical full plan, not only node IDs.
Every failed node requires an error code, an exhausted attempt budget must stop before a
side effect, and an already failed fallback cannot be selected again.

Run plan contract, Runtime budget, workflow registry, and Harness tests after changes.

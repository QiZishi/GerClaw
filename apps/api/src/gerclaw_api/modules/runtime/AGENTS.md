# Runtime Module Instructions

## Responsibility

This module owns immutable execution DTOs, per-turn budgets, fail-closed permission decisions and the governed AgentScope tool registry. It is the only authorization boundary between an agent and a registered tool.

## Invariants

- Unknown tools, version mismatches, missing scopes/roles, unverified patient access, unredacted sensitive egress and critical actions are denied by default.
- High-risk or side-effecting actions require an interactive, durable approval and idempotency key; a downstream tool cannot relax a Runtime verdict.
- Every tool call validates declared Pydantic input/output size and schema, consumes a fresh permission permit and obeys its timeout.
- Budgets, policy versions and capability definitions are server-owned; never accept them from the browser or model.

## Change and test rules

- Add a new capability/version rather than silently broadening an existing permission boundary.
- Run `tests/test_runtime_permission.py`, `tests/test_runtime_registry.py` and `tests/test_runtime_budget.py` for Runtime changes.
- Re-run approval and chat integration tests when approval state, audit data or tool invocation flow changes.

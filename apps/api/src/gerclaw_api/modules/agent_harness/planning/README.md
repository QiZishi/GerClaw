# Planning

Current implementation defines versioned `PlanNode` and `DynamicPlan` boundaries with
unique-node and reference validation. The production Harness still uses its existing bounded
ReAct loop; no parallel planner has been activated.

Failure to validate prevents execution. Stage 3 will inject a planner and add cycle checks,
budget preflight, fallback execution, and checkpoint persistence. Measure success with plan
shape tests, capability-only dependencies, bounded node counts, and no extra work on Quick
routes.

Consumer: the future run orchestrator. Configuration: only injected capability manifests and
resolved budgets. Known limit: contracts validate shape/cycles but do not execute or persist
nodes. Acceptance: invalid references/cycles fail and valid plans serialize deterministically.

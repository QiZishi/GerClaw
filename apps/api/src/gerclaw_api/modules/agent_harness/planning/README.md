# Planning

Current implementation defines versioned `PlanNode` and `DynamicPlan` boundaries with
unique-node, reference, and cycle validation. `ProductionAgentFactory` owns the translation
from the resolved Harness config into an isolated AgentScope `Agent`; the public Harness
injects it through the `AgentFactory` Protocol. The existing bounded ReAct loop remains
active; no parallel planner has been activated.

Failure to validate prevents execution. Stage 3 will inject a planner and add cycle checks,
budget preflight, fallback execution, and checkpoint persistence. Measure success with plan
shape tests, capability-only dependencies, bounded node counts, and no extra work on Quick
routes.

Consumers: the current run-lifecycle executor and the future DAG orchestrator. Configuration:
only the injected model, workflow, capability manifests, and `ResolvedHarnessConfig`. Known
limit: contracts validate shape/cycles but do not execute or persist nodes. Acceptance:
invalid references/cycles fail, valid plans serialize deterministically, and AgentScope
construction remains replaceable without changing the facade.

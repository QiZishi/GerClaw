# Planning

The package defines versioned `PlanNode`/`DynamicPlan` boundaries, the production
`DeterministicPlanner`, ordinal `SAVIActionSelector`, and `ModelBudgetPreflight`.
`ProductionAgentFactory` remains the only translation from resolved Harness configuration into
an isolated AgentScope `Agent`.

Plan shape changes with route, medical intent, attachment count, selected/available
capabilities, and report intent. Quick has only `answer.quick`; Emergency has only the
deterministic safety node; Standard/Deep add attachment, evidence, governed capability, and
answer/report nodes as needed. Every node declares its checkpoint and resource ceiling, while
Runtime remains the accounting authority. The complete plan is persisted inside `AgentRun.plan`
without replacing the resume metadata.

SAVI first removes invalid/redundant actions, then prioritizes mandatory safety or treatment
prerequisites. Remaining ASK/EXAM/ANSWER candidates use bounded ordinal gains and costs; no
fake probability is produced. Equal-value ASK is preferred over EXAM. The model preflight
checks remaining model/tool/token budgets and the provider context window before construction.

Consumers: Chat persists plans and the Harness enforces plan/budget decisions. Configuration:
all thresholds and reserves arrive through `ResolvedHarnessConfig`. Failure semantics:
unavailable capability, invalid DAG, aggregate plan overflow, or model preflight failure stops
the next side effect with a stable code. Known limit: the existing AgentScope ReAct executor
still performs nodes serially rather than scheduling independent DAG branches. Acceptance:
route-sensitive plans, valid capability references, deterministic SAVI fixtures, and zero model
calls after a failed preflight.

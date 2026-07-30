# Planning

The package defines versioned `PlanNode`/`DynamicPlan` boundaries, the production
`DeterministicPlanner`, ordinal `SAVIActionSelector`, `ClinicalDecisionCoordinator`,
`DynamicPlanExecutor`, and `ModelBudgetPreflight`.
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
The selected action changes the production plan: mandatory missing treatment information
produces a deterministic `clinical.ask` node and returns before retrieval or model execution.
Every AgentScope `ModelCallStartEvent` is now a real pre-side-effect boundary: the coordinator
recounts the current Agent state, applied runtime directives, images, consumed Runtime budget,
and output reserve before allowing the provider iterator to advance. Before a tool executes,
Runtime first validates its complete arguments and grants a fresh `ALLOW` permit; only then
does the same policy reserve the result and follow-up model call immediately before the owner
delegate. The result reserve is the smaller of the configured AgentScope result-token limit and
the capability's registered byte ceiling. The current tool proposal has already been charged
by the stream budget, so it is not double-counted. These checks run for each ReAct iteration
rather than only once at turn construction. A capacity rejection becomes private tool feedback
that lets the Agent continue without calling the owner; equivalent AgentScope `error` states
are normalized to public `failed` only if the enclosing attempt is later promoted.

The coordinator derives missing age, allergy status, complete medication list, and
comorbidity/organ-function questions from the actual source-linked state, so this path is
reachable on a new conversation rather than requiring pre-seeded unknowns. Questions are
persisted back into the Run ClinicalState. Uploaded material can select EXAM, while ANSWER
enters the evidence and composition path.

`DynamicPlanExecutor` is the run-time checkpoint authority. A node cannot start until every
declared dependency completed; required nodes must complete before the unique terminal result;
unselected optional capability nodes are recorded as skipped. Selected owner capabilities are
completed only after `GovernedCapabilityRuntime` returns a validated matching result; successful
AgentScope Skill callbacks use the same checkpoint rule. C3 differential directions are
constructed only from sourced, non-conflicted `ClinicalState` facts, explicitly marked as
non-diagnostic, and passed to the model as code-owned constraints rather than model-created
facts.

Consumers: Chat persists plans and the Harness enforces plan/budget decisions. Configuration:
all thresholds and reserves arrive through `ResolvedHarnessConfig`. Failure semantics:
unavailable capability, invalid DAG, aggregate plan overflow, or model preflight failure stops
the next side effect with a stable code. Acceptance: route-sensitive plans, valid capability references, deterministic SAVI
fixtures, enforced checkpoint transitions, source-linked non-diagnostic directions, and zero
model calls after a failed preflight.

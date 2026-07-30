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

`plan-execution-v1` 是可序列化的无正文 checkpoint：为每个精确 node ID 保存
`pending/running/completed/failed/skipped`、有界单调 attempt、稳定错误码和实际采用的已声明 fallback。
失败节点可从同一步骤重试；required 节点只有自身完成，或其声明 fallback 完成后才算满足。依赖与 fallback
共同构成无环恢复图。快照用完整 `DynamicPlan` 的 canonical SHA-256 绑定 route、capability、required、
dependency、fallback、budget 和 output schema；只复用 node ID 也不能跨计划恢复。多 fallback 按声明
顺序各尝试一次，不会反复执行已失败的第一项；attempt=50 会在下一次副作用前拒绝。快照节点集合、
错误码或 fallback 历史与冻结计划不一致时拒绝恢复。Planning
只拥有状态转换和校验合同，数据库持久化仍由 Run Lifecycle 负责。

Fallback execution is single-owner and depth-first. A source cannot retry after its fallback
lineage starts, a historical fallback cannot be restarted through the ordinary capability
entry, and a parent sibling cannot run while nested recovery is active or has satisfied the
branch. If the next declared fallback can never start because a dependency is irrecoverably
failed/skipped or its attempt budget is exhausted, `skip_unavailable_fallback` records that
specific node as `skipped` in the lineage before the next sibling becomes eligible. General
optional skipping remains private to successful finalization, so it cannot destroy a failed
required node's recovery path.

Production governance exposes observer-backed async transitions for checkpoint, completion,
failure, fallback start, unavailable-fallback skip, optional capability completion, and
finalization. The Run persistence observer must finish before the owner side effect starts;
observer failure aborts the operation. Synchronous executor methods remain deterministic unit
primitives and are not the production orchestration entry.

Consumers: Chat persists plans and the Harness enforces plan/budget decisions. Configuration:
all thresholds and reserves arrive through `ResolvedHarnessConfig`. Failure semantics:
unavailable capability, invalid DAG, aggregate plan overflow, or model preflight failure stops
the next side effect with a stable code. Acceptance: route-sensitive plans, valid capability references, deterministic SAVI
fixtures, enforced checkpoint transitions, source-linked non-diagnostic directions, and zero
model calls after a failed preflight.

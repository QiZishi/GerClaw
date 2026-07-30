# Plugin Runtime Instructions

Owns governed capability manifests, selection boundaries, and reusable result references.
It never reimplements CGA, medication review, prescription, report, Runtime, RAG, or Skill.

Only allowlisted manifests may execute. Validate input/output at the boundary, respect
Runtime permissions and risk levels, and reuse actor/session-scoped results. Never load
arbitrary Python, remote code, prompts, or sibling-project paths.

An owner capability must never run before its actor-owned Run and plan-node `running`
checkpoint are durable. Commit a validated result and the node's `completed` transition in
one fenced transaction. Treat owner capabilities as idempotent because a process can stop
after the owner side effect and before result persistence. Optional owner failures must not
replace or contaminate an otherwise valid answer; retain only bounded private warning metadata
and use `completed_with_warnings`. Never inject an owner invoker when durable Run persistence
is absent. A selected owner node may reach `completed` only when its validated result already
exists in the encrypted plan or commits atomically with that transition.

Run capability manifest, Runtime permission, workflow registry, shared-result, checkpoint,
atomic result-persistence, and warning-terminal tests.

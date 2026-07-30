# Evolution Governance

This package turns Stage 6's dual-track rules into executable, versioned contracts.
`OBJECT_RULES` classifies persistent object kinds by authority rather than directory name;
`COMPONENT_CHARTERS` records the core purpose and non-negotiable mechanisms of each Harness
component. `REQUIRED_CHARTERS_BY_OBJECT_KIND` is the single mapping from each offline-evolvable
kind to the Charter observations its evaluator must actually produce. `EvolutionGovernancePolicy`
classifies low-authority content, rejects authority
escalation and mixed-track candidates, and declares immutable human approval unconditional.
The production rule/charter mappings are read-only and cannot be replaced through constructor
injection. Each evolvable kind is also bound to a trusted target namespace, so a candidate
cannot label `policy/prompt/**` as a presentation Skill to acquire mutable-track treatment.

Memory facts, preferences, and workspace habits remain mutable online content. Clinical
Memory is still low-authority user context and must pass its existing proposed/confirmed,
conflict, revision, expiry, provenance, and recall gates. Presentation and bounded-retrieval
Skill versions may evolve online; clinical, tooling, Prompt, routing, and planning changes
are offline proposals. Safety gates, Runtime permissions, auth, charters, evaluators, sealed
cases, keys, audit logs, release refs, and credentials cannot be candidate changes.

The policy classifies content only after the Memory or Skill owner has verified the actual
actor/resource relationship. It intentionally accepts no caller-provided ownership boolean.
Repository-backed Memory and Skill owner services now call this classifier only after
verifying the actor/resource relationship. Memory CRUD keeps its online mutable-content
semantics, while Skill evolution applies only the fixed low-risk directive DSL online and
routes every other candidate to offline review.

This package is intentionally read-only. Candidate storage, worktree/symlink checks, sealed
attestation, evaluation, approval signatures, and atomic promotion belong to the separate
operator-run `apps/evolution` trust domain. That controller copies and verifies this manifest
outside the candidate worktree; the in-process manifest alone is not treated as a complete
trust boundary. This package does not accept a caller-provided `approved=True` as proof of
approval.

Acceptance requires the four mandatory counterexamples, unknown-kind fail-closed behavior,
path traversal rejection, unique charters/rules, immutable approval despite a disabled
deployment flag, and the existing component tests. The offline controller must continue to
verify real sealed attestations and signed approvals; evaluator IDs alone are never accepted
as evidence that those gates ran.

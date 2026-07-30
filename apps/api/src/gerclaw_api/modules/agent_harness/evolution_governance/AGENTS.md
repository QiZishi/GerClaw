# Evolution Governance Instructions

Owns the read-only dual-track classification manifest and component charters. It does not
write Memory, Skill, candidates, approvals, releases, or production configuration.

## Core mechanism that must not be changed

- Classification is by `track`, `authority`, owner, and update policy, not by a filename.
- Unknown object kinds default to `immutable`; no unknown kind can mutate online.
- Mutable Memory content and low-risk Skill content remain online, revisioned, actor-owned
  CRUD. They never receive control-plane authority.
- Component charters, this policy, safety/authorization/Runtime gates, sealed evaluators,
  approval keys, audit logs, release refs, and credentials are candidate-non-writable.
- Immutable approval is required even when ordinary candidate approval is disabled.
- A candidate may contain exactly one track. Path traversal and duplicate targets fail closed.
- Candidate-declared object kinds never determine authority by themselves; every target must
  match the trusted namespace bound to that kind.

This classifier never accepts ownership claims from an API or model. The Memory/Skill owner
service must first prove tenant/actor/resource ownership from its repository and only then
request content classification.

The production manifest is candidate-readable where safe, but the Stage 6 offline controller
must copy its trusted digest outside the candidate worktree before evaluation. Run governance
counterexamples and component-boundary tests after every change.

This package may declare that approval is required; it must not accept a bare boolean as
approval evidence. Proposal/track/commit/approver/time/signature verification belongs to the
sealed offline controller.

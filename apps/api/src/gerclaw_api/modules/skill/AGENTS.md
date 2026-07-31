# Skill Module Instructions

## Responsibility

This module owns the lifecycle of declarative GerClaw Skills: validation, registry, archival, loading, constrained execution, reviewable model-generated drafts and dual-track evolution. It does not permit arbitrary code, shell, network calls or privilege escalation.

## Invariants

- A Skill is data and untrusted instruction content. It cannot alter system policy, role, medical safety, permissions, evidence rules or the governed-tool allowlist.
- IDs, versions, parameter schemas and tool lists are validated server-side. A new version is required for behavior changes to a registered Skill.
- A loaded Skill must pass a server-derived, exact `security_evaluation`
  profile before AgentScope receives it. The profile is derived only from the
  validated ID, SemVer and declared allowlisted tools; it is never supplied by
  the browser, model, or Skill Markdown.
- Only declared, allowlisted tools run through the Runtime boundary; generated drafts are parsed and revalidated before registration.
- Model-generated drafts accept only strict `skill-generation-model-output-v1`
  via the shared versioned output contract; missing, stale or extra provider
  fields may not reach Markdown serialization or manual review.
- Built-in assets remain declarative and auditable. Do not turn a `SKILL.md` into executable code or a source of medical facts without local evidence.
- Online evolution authority is derived from the actual owner-scoped current
  definition and validated candidate diff. Browser/model category labels cannot
  grant authority. Online presentation/retrieval changes must use the exact
  server-owned directive DSL; every free-text instruction, name/category/tool/
  parameter change remains immutable. Clinical, permission and unknown changes
  remain immutable-track proposals whose content cannot cross the online API.
- Every persistent source-Markdown write uses that same policy. Register,
  upload, explicit PATCH and model-driven evolve are not separate trust
  boundaries and may not bypass classification. A first low-authority exact-DSL
  definition may become active online; an immutable first definition creates an
  inert hidden baseline plus an encrypted proposal. An immutable PATCH leaves
  the active revision unchanged. An owner toggling only `enabled` remains
  ordinary CRUD because it does not change the Skill definition.
- An immutable candidate is not discarded or regenerated later. Persist it once
  with its exact encrypted base/candidate snapshots, owner, trace, request
  fingerprint, revisions and digest in the append-only proposal ledger. The
  online API may expose only the content-free receipt; it cannot approve,
  activate, edit or execute that proposal.

## Change and test rules

- Preserve archive/revision readability and tenant/actor access boundaries when changing registry or storage behavior.
- Keep the hidden baseline for a first immutable candidate non-listable,
  non-loadable, disabled and non-executable. Do not expose its reserved internal
  category as a product Skill or allow it to satisfy a session selection.
- Evolution may target only a caller-owned custom Skill at its current revision
  and must preserve the ID and increase SemVer. An online-admitted mutation must
  preserve the existing tool list, parameter schema and enabled state, pass the
  central governance manifest, use only fixed directives, and use optimistic
  revision control. Immutable candidate content must not change the production
  record, current conversation, online editor or response payload. Do not add
  update/delete methods to the proposal repository; later review-state changes
  belong in a separate append-only review event model.
- Run `tests/test_skill_contract.py`, `tests/test_skill_module.py`, `tests/test_skill_api.py` and integration coverage as applicable.
- Update the specific built-in Skill folder's `AGENTS.md` and `SKILL.md` together when its intended workflow changes.

# Skill Module Instructions

## Responsibility

This module owns the lifecycle of declarative GerClaw Skills: validation, registry, archival, loading, constrained execution, reviewable model-generated drafts and review-only evolution drafts. It does not permit arbitrary code, shell, network calls or privilege escalation.

## Invariants

- A Skill is data and untrusted instruction content. It cannot alter system policy, role, medical safety, permissions, evidence rules or the governed-tool allowlist.
- IDs, versions, parameter schemas and tool lists are validated server-side. A new version is required for behavior changes to a registered Skill.
- Only declared, allowlisted tools run through the Runtime boundary; generated drafts are parsed and revalidated before registration.
- Model-generated drafts accept only strict `skill-generation-model-output-v1`
  via the shared versioned output contract; missing, stale or extra provider
  fields may not reach Markdown serialization or manual review.
- Built-in assets remain declarative and auditable. Do not turn a `SKILL.md` into executable code or a source of medical facts without local evidence.

## Change and test rules

- Preserve archive/revision readability and tenant/actor access boundaries when changing registry or storage behavior.
- Evolution may target only a caller-owned custom Skill at its current revision; it must preserve the ID, increase SemVer and return a draft only. It must never overwrite, enable or publish a Skill.
- Run `tests/test_skill_contract.py`, `tests/test_skill_module.py`, `tests/test_skill_api.py` and integration coverage as applicable.
- Update the specific built-in Skill folder's `AGENTS.md` and `SKILL.md` together when its intended workflow changes.

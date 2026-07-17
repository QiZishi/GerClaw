# Security Evaluation Module Instructions

## Responsibility

This module owns immutable, version-bound security-risk profiles and the
fail-closed pre-enable gate for Runtime assets. The first production consumer
is the governed Chat toolkit: `search_knowledge`, `search_memory`, and
`web_search` cannot be registered without a matching active profile.

## Invariants

- A profile is server-owned, strict, version-bound and keyed by exact asset
  kind/name. Browser, model, Skill and retrieved content can never provide or
  alter a profile.
- Runtime tool capability risk, network access, data classes and version must
  match its profile. Unknown, blocked or broadened tools fail closed before an
  AgentScope toolkit is built.
- Every profiled tool declares schema, output-boundary, permission, timeout
  and budget controls. Patient-scoped tools additionally require the Runtime
  ownership gate; external tools additionally require egress-redaction proof.
- The profile is an executable admission control, not evidence of clinical
  validity, complete red-team coverage or completed privacy lifecycle work.

## Change and test rules

- Add a new reviewed profile/version before enabling a new Runtime tool or
  broadening a capability; never silently reuse a profile with looser fields.
- Run `tests/test_security_evaluation.py` and `tests/test_runtime_registry.py`.
- Keep residual-risk text free of patient data, prompts, secrets and provider
  responses. Do not make this module an alternate authorization engine.

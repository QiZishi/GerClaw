# Offline Evolution Controller Instructions

This application is a separate, operator-run trust domain. It is not imported by FastAPI,
copied into the production API image, or callable by the online Agent.

## Trust boundary

- Official optimizer identity is an exact repository URL, immutable commit, reference name,
  declared license, evidence path, and evidence digest.
- A familiar package or directory name is not availability proof. Missing or mismatched
  source is reported as `unavailable`; never substitute a local implementation.
- Candidate worktrees, optimizer processes, and online signals are untrusted inputs.
- Sealed cases, thresholds, attestation/approval keys, audit logs, release refs, and
  deployment credentials must live outside candidate-readable roots.
- Every attestation key is authority-bound to one evaluator version, sealed case-set digest,
  gate-policy digest, and promotion-active state; key ID is part of the signed domain.
- The controller may import versioned governance contracts from `apps/api`; it must not copy
  or reinterpret their object-authority rules.

## Non-negotiable behavior

- No network fetch, package install, candidate execution, promotion, or rollback occurs from
  source inspection alone.
- Never log secrets, sealed case content, user content, clinical content, or Provider payloads.
- Every unavailable result uses a bounded reason code and contains no raw subprocess output.
- Never trust supplied paired-gate booleans; recompute every per-case/slice/charter gate from
  baseline and candidate observations before signing and again before promotion.
- Production dependencies must remain free of A-Evolve, GEPA, Adaptive Auto-Harness, training,
  or benchmark packages.

Run the app-local unit tests, Ruff, and Mypy after each module change. Supply-chain pin changes
also require a human review of the upstream repository, commit, license evidence, and date.

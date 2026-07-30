# Offline Evolution Controller Instructions

This application is a separate, operator-run trust domain. It is not imported by FastAPI,
copied into the production API image, or callable by the online Agent.

## Trust boundary

- Official optimizer identity is an exact repository URL, immutable commit, reference name,
  declared license, evidence path, and evidence digest.
- A familiar package or directory name is not availability proof. Missing or mismatched
  source is reported as `unavailable`; never substitute a local implementation.
- Candidate worktrees, optimizer processes, and online signals are untrusted inputs.
- Candidate code may execute only through the exact OS sandbox executor accepted by the
  production runner; there is no same-UID/local subprocess fallback. The controller exports the
  named commit with `git archive`, binds its digest into the run, copies it through a
  controller-owned Docker volume, verifies the digest before extraction, and never mounts a live
  worktree. Ignored/untracked files and `.git` therefore cannot enter execution. The sandbox uses
  a content-addressed preinstalled image, read-only source, isolated tmpfs, no network,
  capabilities or privilege escalation, bounded CPU/memory/PIDs/files/output/time, and
  process-group/container/volume cleanup. Controller source, keys, sealed cases, audit storage,
  release refs, Docker socket, and host credentials are never mounted or passed.
- Container and volume cleanup is a verified terminal step. The controller retries exact-name
  removal and confirms absence; an unconfirmed cleanup raises
  `EVOLUTION_SANDBOX_CLEANUP_FAILED` for operator repair instead of reporting an ordinary
  candidate failure.
- Sealed cases, thresholds, attestation/approval keys, audit logs, release refs, and
  deployment credentials must live outside candidate-readable roots.
- Every attestation key is authority-bound to one evaluator version, sealed case-set digest,
  gate-policy digest, and promotion-active state; key ID is part of the signed domain.
- Automated evaluation and human approval use different keys and envelopes. Human approval
  uses an Ed25519 private key in a separately authenticated signer; promotion receives only the
  public verification key and exposes no signing API. Approval identity and time come from the
  signer authority and trusted clock, never candidate input or an `approved` boolean.
- The controller may import versioned governance contracts from `apps/api`; it must not copy
  or reinterpret their object-authority rules.

## Non-negotiable behavior

- No network fetch, package install, candidate execution, promotion, or rollback occurs from
  source inspection alone.
- Never log secrets, sealed case content, user content, clinical content, or Provider payloads.
- Every unavailable result uses a bounded reason code and contains no raw subprocess output.
- Never trust supplied paired-gate booleans; recompute every per-case/slice/charter gate from
  baseline and candidate observations before signing and again before promotion.
- An evaluation declares only component charters it actually executed. The paired gate requires
  the trusted charter set for every affected object kind; unaffected charters are not fabricated
  as passing observations.
- Promotion revalidates the frozen candidate, sealed gate, approval authority, approval
  freshness, and current signed release ledger. Release, ledger, immutable record, and consumed
  ticket refs move in one Git ref transaction; immutable-track approval cannot be disabled.
- Rollback targets only a public-key-verified record already present in the atomic release
  ledger. External audit mirrors may degrade without undoing a committed release; the signed
  Git ledger remains the repair source and the warning must be retained for operators.
- Production dependencies must remain free of A-Evolve, GEPA, Adaptive Auto-Harness, training,
  or benchmark packages.

Run the app-local unit tests, Ruff, and Mypy after each module change. Supply-chain pin changes
also require a human review of the upstream repository, commit, license evidence, and date.

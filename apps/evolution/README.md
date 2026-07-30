# GerClaw Offline Evolution

`apps/evolution` is an operator-run environment for Stage 6 candidate isolation, paired
evaluation, sealed attestation, approval, promotion, and rollback. It is outside
`apps/api`'s Docker build context, so the production API image does not receive this package
or any optimizer/benchmark dependency.

The first implemented boundary is the official-source registry. It pins the official
A-Evolve, GEPA, and Adaptive Auto-Harness repository, immutable commit, reference, declared
license, and license-evidence digest. Inspection is local and fail closed: a checkout is
`available` only when its canonical path is a Git checkout whose `origin`, clean `HEAD`, and
committed license evidence all match the pin. The inspector reads evidence from the Git
object, not the mutable working file.

An absent checkout is a normal `unavailable` result. This application deliberately does not
download an optimizer and does not provide a same-name fallback. Operators install a pinned
source into an isolated environment only after supply-chain review.

Current limitations: source availability does not authorize execution, and a verified
optimizer still has no access to sealed assets or production credentials. Candidate
worktrees, paired evaluation, sealed HMAC attestation, approval, atomic promotion, and
rollback are subsequent modules in this same isolated application.

Effectiveness is measured by deterministic source-pin tests, negative tests for wrong
remote/commit/license evidence/dirty checkout, production image inspection, and an audited
candidate lifecycle. A source-pin update is accepted only with an upstream review date and
an immutable Conventional Commit.

# GerClaw Offline Evolution

`apps/evolution` is an operator-run environment for Stage 6 candidate isolation, paired
evaluation, sealed attestation, approval, promotion, and rollback. It is outside
`apps/api`'s Docker build context, so the production API image does not receive this package
or any optimizer/benchmark dependency.

The official-source registry pins the official
A-Evolve, GEPA, and Adaptive Auto-Harness repository, immutable commit, reference, declared
license, and license-evidence digest. Inspection is local and fail closed: a checkout is
`available` only when its canonical path is a Git checkout whose `origin`, clean `HEAD`, and
committed license evidence all match the pin. The inspector reads evidence from the Git
object, not the mutable working file.

Candidate isolation uses a detached Git worktree beneath a controller-owned root. Freeze
reads the committed diff and blob modes from Git, requires the base to be an ancestor, and
binds every actual file to the central logical object-kind/target policy. Unlisted files,
deletions, renames/copies, symlinks, submodules, path traversal, kind/path disguises, dirty
state, a changed HEAD, and a forged freeze manifest fail closed. The governance manifest and
all content digests are copied into `frozen-candidate-v1` outside the candidate worktree.

Paired evaluation consumes only bounded, content-free observations for the same cases and
four mandatory slices (`normal`, `complex`, `high_risk`, `elderly`). A passed baseline case
cannot fail, no individual case or slice may lose quality, real runtime paths must activate,
and every component charter must pass. Baseline and candidate use the exact same runner,
version, and evaluation-profile digest. Case IDs are opaque HMAC-style identifiers rather
than descriptive labels. These public gates are not sufficient for release: an out-of-process
sealed evaluator signs the freeze digest, report digest, sealed case-set digest,
Token/latency verdicts, runtime activation, and charter verdicts with a controller-only HMAC
key. Neither sealed cases nor thresholds appear in the report.

The signer and verifier independently recompute the paired gate from observations; an
all-green gate object supplied over regressing results is rejected. Each HMAC key record is
bound to one exact evaluator/case-set/gate-policy profile and an explicit promotion-active
state. The HMAC domain includes the envelope schema and key ID, so an old, staging, or
lower-authority key cannot relabel itself as the current medical evaluator.

An absent checkout is a normal `unavailable` result. This application deliberately does not
download an optimizer and does not provide a same-name fallback. Operators install a pinned
source into an isolated environment only after supply-chain review.

Current limitations: source availability, freeze, and even a valid sealed evaluation do not
authorize release, and a verified optimizer still has no access to sealed assets or
production credentials. Human approval, atomic promotion, and rollback are subsequent
modules in this same isolated application.

Effectiveness is measured by deterministic source-pin tests, negative tests for wrong
remote/commit/license evidence/dirty checkout, production image inspection, and an audited
candidate lifecycle. A source-pin update is accepted only with an upstream review date and
an immutable Conventional Commit.

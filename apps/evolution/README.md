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

Candidate execution is a separate trust boundary, not an ordinary subprocess. The paired runner
accepts only the exact Docker executor and has no production local-execution fallback. The
executor exports the evaluated commit from Git objects, records the archive digest, stages it in
a controller-owned Docker volume, verifies that digest inside the container, and extracts it to
read-only runtime source. It never mounts the live worktree, so ignored/untracked files, `.git`,
and host-side transient edits cannot become evaluated code. The content-addressed preinstalled
image runs with no network, read-only root and bundle volume, no capabilities or privilege
escalation, an isolated tmpfs, non-root UID, bounded CPU/memory/PIDs/open files/output/time, and
forced container/process-group/volume cleanup. Controller source, source repository, Docker
socket, keys, sealed cases, release refs, audit logs, host environment, and Provider credentials
remain invisible. Cleanup retries exact resource names and queries Docker to confirm their
absence; failure becomes bounded operator-repair state rather than being silently swallowed.
Each run binds the frozen manifest and exact execution-bundle digest.
The Skill runner's evaluation-profile digest also binds the exact controller-supplied process
script SHA-256; changing the code that actually runs inside Docker cannot retain the old
profile identity.

Paired evaluation consumes only bounded, content-free observations for the same cases and
four mandatory slices (`normal`, `complex`, `high_risk`, `elderly`). A passed baseline case
cannot fail, no individual case or slice may lose quality, real runtime paths must activate,
and every applicable, actually executed component charter must pass. The paired gate derives
the required Charter set from the affected object kinds; the runner never fabricates unrelated
Charters as passing. Baseline and candidate use the exact same runner, version, and
evaluation-profile digest. Case IDs are opaque HMAC-style identifiers rather than descriptive
labels. These public gates are not sufficient for release: an out-of-process
sealed evaluator signs the freeze digest, report digest, sealed case-set digest,
Token/latency verdicts, runtime activation, and charter verdicts with a controller-only HMAC
key. Neither sealed cases nor thresholds appear in the report.

The signer and verifier independently recompute the paired gate from observations; an
all-green gate object supplied over regressing results is rejected. Each HMAC key record is
bound to one exact evaluator/case-set/gate-policy profile and an explicit promotion-active
state. The HMAC domain includes the envelope schema and key ID, so an old, staging, or
lower-authority key cannot relabel itself as the current medical evaluator.

Automated validation never becomes approval. `human-approval-proof-v1` is created only by a
separately authenticated, human-controlled Ed25519 signing service and binds the accountable
approver principal, ticket, candidate commit, track, freeze, paired report, sealed attestation,
and a trusted-clock time. The promotion-side verifier contains public keys only and exposes no
approve/sign operation. The API accepts neither `approved=true`, a caller-provided approver
identity, nor a caller-provided timestamp. It re-verifies the sealed gate and enforces
freeze → paired evaluation → sealed evaluation → approval ordering. Inactive keys and keys
whose allowed tracks exclude the proposal fail closed; immutable approval therefore cannot be
disabled by an ordinary deployment flag.

The final Skill activation authorization additionally signs the current governance-manifest
digest. Production verifies it against its own manifest before loading proposal state, and
revalidates the candidate parser/policy under a locked owner record. Idempotent replay requires
both the same approval ticket and the same complete authorization digest; a different grant
cannot borrow a previous terminal event. A stale result reports the locked record's actual
revision when that record still exists.

An absent checkout is a normal `unavailable` result. This application deliberately does not
download an optimizer and does not provide a same-name fallback. Operators install a pinned
source into an isolated environment only after supply-chain review.

Promotion revalidates the clean frozen worktree, sealed gate, public-key human approval,
trusted time ordering, freshness, and the current signed release ledger. A single Git
`update-ref --stdin` transaction moves the release ref, ledger pointer, immutable signed record,
and one-time approval-ticket ref together. Immutable-track approval is unconditional; mutable
approval remains a deployment policy. The external JSONL audit mirror is append-only. If that
mirror is temporarily unavailable, the atomic signed Git ledger remains authoritative and the
result is explicitly `repair_required` rather than falsely reporting that the release failed.

Rollback accepts only a valid Ed25519 release record already referenced by the immutable release
record namespace. It creates a new signed history entry and atomically moves the release and
ledger refs; arbitrary commits and merely well-formed but unreleased records are rejected.

Current limitation: the release signer, human signer, sealed evaluator, Git ref protection, and
external audit mirror still require deployment as separate identities/roots. Repository code
enforces their contracts but cannot replace branch protection, HSM/enterprise approval, or
operating-system permissions.

Effectiveness is measured by deterministic source-pin tests, negative tests for wrong
remote/commit/license evidence/dirty checkout, production image inspection, and an audited
candidate lifecycle. A source-pin update is accepted only with an upstream review date and
an immutable Conventional Commit.

# Evidence

Current implementation defines the versioned `EvidenceRecord` admission boundary and an
injected `EvidenceAdmissionPolicy`. Local results are admitted only after the
`local-rag-evidence-v1` provenance contract, absolute relevance threshold, source-authority
ordering (`guideline` → `consensus` → `textbook` → `literature`), and ID/adopted-text
deduplication. Retrieval remains owned by `rag`; no duplicate retriever was introduced.
Model-facing `[E#]`, `[W#]`, and `[A#]` markers are range-checked against the exact admitted
local, web, and owner-scoped upload lists in the same answer segment. They are normalized to
reserved `[C#]` markers before
any SSE text becomes public, so streamed and terminal citation positions are identical. A
model cannot emit `[C#]` directly. Reserved, missing, or out-of-range model markers—including
common spaced forms such as `[ E1 ]`—are removed without inventing a source. A candidate with
an unbound clinical claim is privately regenerated once; if the replacement still lacks an
in-segment citation, only that claim is removed and the remaining useful answer is promoted.
A malformed server-owned public marker still fails closed.
One valid citation elsewhere in an answer cannot unlock an unrelated clinical claim.
The terminal `ClaimEvidenceAudit` binds each detected clinical claim to source IDs, locators,
and hashes of the exact adopted excerpts. The client creates an inline citation control only
for server-owned `[C#]` markers.

Invalid, incomplete, or below-threshold records fail closed. The public citation excerpt is
the exact bounded `adopted_text`; absent institution/version metadata stays absent internally
instead of being invented. If all local results are rejected, the Harness enters its existing
deterministic evidence-unavailable path before a model call.

Consumers: Harness planning/answer gates and the prescription citation adapter; RAG/Search/
Document remain evidence producers through existing adapters. Configuration:
`GERCLAW_AGENT_EVIDENCE_MIN_SCORE` and `GERCLAW_AGENT_EVIDENCE_TOP_K` are resolved once at
composition. The shipped absolute relevance floor is `0.3`; deployments may raise it after
paired retrieval evaluation, but lowering it requires evidence-quality regression review.
Known limit: web and uploaded evidence retain their owner-specific admission
adapters; persistent evidence rows and richer citation UI metadata are future work.
Acceptance: every admitted local record resolves to a validated locator and exact adopted
text, higher-authority sources sort first, duplicates are removed, every preserved clinical
claim—including a claim based on the current upload—has an in-segment binding, streamed text
equals terminal text, and zero fabricated
citations are emitted.

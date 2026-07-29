# Evidence

Current implementation defines the versioned `EvidenceRecord` admission boundary and an
injected `EvidenceAdmissionPolicy`. Local results are admitted only after the
`local-rag-evidence-v1` provenance contract, absolute relevance threshold, source-authority
ordering (`guideline` → `consensus` → `textbook` → `literature`), and ID/adopted-text
deduplication. Retrieval remains owned by `rag`; no duplicate retriever was introduced.

Invalid, incomplete, or below-threshold records fail closed. The public citation excerpt is
the exact bounded `adopted_text`; absent institution/version metadata stays absent internally
instead of being invented. If all local results are rejected, the Harness enters its existing
deterministic evidence-unavailable path before a model call.

Consumers: Harness planning/answer gates and the prescription citation adapter; RAG/Search/
Document remain evidence producers through existing adapters. Configuration:
`GERCLAW_AGENT_EVIDENCE_MIN_SCORE` and `GERCLAW_AGENT_EVIDENCE_TOP_K` are resolved once at
composition. Known limit: web and uploaded evidence retain their owner-specific admission
adapters; persistent evidence rows and richer citation UI metadata are future work.
Acceptance: every admitted local record resolves to a validated locator and exact adopted
text, higher-authority sources sort first, duplicates are removed, and zero fabricated
citations are emitted.

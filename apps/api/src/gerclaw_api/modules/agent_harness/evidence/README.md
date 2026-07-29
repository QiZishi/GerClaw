# Evidence

Current implementation defines the versioned `EvidenceRecord` admission boundary. Existing
retrieval and citation conversion remain in `rag`, `search`, `document`, and `safety`; no
duplicate retriever was introduced.

Invalid or incomplete records fail closed. Stage 4 adds source ranking, absolute relevance,
deduplication, and adopted-text verification. Measure improvement with citation-to-source
resolution, locator verification, zero fabricated citations, and truthful degradation.

Consumers: future planning/answer gates; current RAG/Search/Document remain producers through
existing adapters. Configuration: ranking thresholds will be resolved and injected. Known
limit: the contract is not yet the active citation store. Acceptance: every admitted record
has locator, adopted text, applicability, and verified/degraded status.

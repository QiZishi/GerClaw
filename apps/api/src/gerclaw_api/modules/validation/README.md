# Validation

`validation` centralizes versioned contracts at cross-module boundaries. Its
production consumers are:

- `public-chat-sse-v1`: Harness events are validated before callback delivery,
  and public events are validated again immediately before entering the FastAPI
  SSE queue.
- `local-rag-evidence-v1`: `HybridRAGModule` validates every returned local
  chunk's provenance; the AgentScope adapter, public citation projection and
  RAG eval runner reuse that exact schema. Malformed metadata is excluded and
  cannot be repaired with invented chapter or chunk locations.

The module uses strict Pydantic schemas. It owns transport shape, bounds and
compatibility versioning; Chat, Runtime and medical modules retain ownership of
their domain semantics. A malformed payload raises
`StreamContractValidationError` or `RAGEvidenceContractValidationError`, whose
public handling is deliberately generic and does not echo the rejected data.

Current scope is deliberately narrow and real. HTTP, model structured output,
tool parameters/results, memory, voice and export boundaries continue to use
their existing strict contracts and are listed for incremental migration in the
requirements matrix.

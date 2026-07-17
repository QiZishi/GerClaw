# Validation

`validation` centralizes versioned contracts at cross-module boundaries. The
first production consumer is `public-chat-sse-v1`: Harness events are validated
before callback delivery, and public events are validated again immediately
before entering the FastAPI SSE queue.

The module uses strict Pydantic schemas. It owns transport shape, bounds and
compatibility versioning; Chat, Runtime and medical modules retain ownership of
their domain semantics. A malformed payload raises
`StreamContractValidationError`, whose public handling is deliberately generic
and does not echo the rejected data.

Current scope is deliberately narrow and real. Other API, model, tool, RAG,
memory, voice and export boundaries continue to use their existing strict
contracts and are listed for incremental migration in the requirements matrix.

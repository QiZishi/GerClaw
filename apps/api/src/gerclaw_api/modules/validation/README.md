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
- Versioned model output: `validate_versioned_model_output` and its JSON
  counterpart reject model projections unless their strict domain schema and
  literal `model_output_schema_version` match the caller's declared version.
  Production consumers include five-prescription generation
  (`five-prescription-model-output-v1`), chat-native intake extraction
  (`prescription-intake-model-output-v1`), Memory extraction
  (`memory-extraction-model-output-v1`) and Skill generation/evolution
  (`skill-generation-model-output-v1`).
- Public Voice transport is explicitly versioned as `voice-asr-response-v1`
  (strict ASR JSON) and `voice-tts-pcm16-v1` (PCM16 media header). The BFF
  allowlists the contract header and the browser verifies its exact value
  before decoding either response.

The module uses strict Pydantic schemas. It owns transport shape, bounds and
compatibility versioning; Chat, Runtime and medical modules retain ownership of
their domain semantics. A malformed payload raises
`StreamContractValidationError`, `RAGEvidenceContractValidationError` or
`ModelOutputContractValidationError`, whose public handling is deliberately
generic and does not echo the rejected data.

Current scope is deliberately narrow and real. HTTP, tool parameters/results
and export boundaries continue to use their existing strict contracts and are
listed for incremental migration in the requirements matrix.

## 维护与演进

**可安全改进。** 可将 HTTP、工具参数/结果和 export 逐步迁入版本化 contracts；每次迁移先声明 literal version、strict schema、生产 consumer、错误映射与兼容淘汰窗口，再用生产边界测试证明接线。

**不可破坏的契约。** validation 只拥有 transport shape、bounds 和 compatibility，不替代领域医学判断；未知字段、旧/缺版本和 malformed payload 必须受控失败，不能以默认值修补 provenance 或模型输出。公共错误不得回显被拒绝的数据。

**性能与回归验收。** 每个 contract 有合法、未知字段、缺/错版本、边界大小和 public-error 回归；producer 与 consumer 都要验证。最大合法 SSE/模型/voice payload 的验证应保持线性并记录 p95；10 并发流不得因单个 malformed event 影响其他连接。

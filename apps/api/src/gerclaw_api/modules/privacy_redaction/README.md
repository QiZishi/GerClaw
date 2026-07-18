# Privacy Redaction

`privacy_redaction` is the server-owned privacy boundary for text that may be
sent to an external service. `redact_external_search_query()` returns a
versioned safe query and PHI-free category counts. It preserves only the
clinical search intent; it never stores or exposes a reversible mapping.

The current `1.1.0` policy removes labelled Chinese/English names, mainland
China phone numbers, ID-card numbers, email addresses, common credential
assignments and control characters. `external_search_query` preserves search
intent using “患者”; `external_tts` uses “您” for a safer spoken projection.
Both fail closed on empty or overlong input. The policy has no network,
database or medical-decision dependency.

Current text-redaction scope is external online-search query and FastAPI TTS
egress. FastAPI TTS writes an internal, PHI-free `prepared → succeeded|failed`
provider record before/after egress; it contains only purpose, processor,
policy version and per-field category counts. FastAPI ASR has a separate,
non-redaction `audio-egress-v1` record with the fixed audio purpose, processor,
outcome and an empty findings list. It does not assert that audio is
de-identified, safe to send, or consented. The Next.js MinerU BFF records an
owner-bound `external_document_parse` decision before the provider starts and
finishes it after the provider outcome. Its `document-egress-v1` record has no
filename, document text, size, page count or findings, and it does not assert
that the document is de-identified, safe to send, or consented. The legacy
Next.js TTS BFF, exports, AgentScope internal search and a
user-facing processing ledger still require their own purpose-specific adapters
before they can claim unified coverage.

Before every AgentScope model-provider attempt, `FailoverChatModel` also creates
an in-memory, provider-bound copy of every message and applies the distinct
`external_model_prompt` `1.0.0` projection to each nonblank string field. This preserves
message and tool-block structure while removing identifiers and credentials;
oversized values fail closed. The local Agent state, encrypted history and
document store are not mutated. Each configured model slot persists an
owner-bound `prepared → succeeded|failed` record in `provider_egress_events`
before/after its attempt. The record contains only the logical slot,
`external_model_prompt` policy version and category counts; it contains no
provider identity, prompt text or model output. This audit is not consent
management or a user-facing processing ledger.

`modules/evals` has six reviewed `privacy-redaction-case-v1` synthetic canaries:
four cover the `1.1.0` search/TTS policy and two cover the `1.0.0` model-prompt
projection, including Markdown preservation. The runner rejects ASR and document
purposes instead of misrepresenting their non-text egress records as text
redaction coverage.

## 维护与演进

**可安全改进。** 在核心业务稳定后，可按 provider boundary 增加字段级分类、同意、透明度、生命周期和 OCR/ASR 误漏评测；新 purpose 必须有版本化 policy、最小审计字段和离线合成 canary，不能复用不适配的文本策略。

**不可破坏的契约。** 任何外发必须先写 prepared 决策，审计写入失败即不外发；日志、Trace 和 outcome 不得保存正文、图片、文件名、provider body 或 key。不得把 ASR/文件的无文本 outcome 误称为已经脱敏或取得同意。

**性能与回归验收。** 每个 policy version 必测允许/拒绝、Markdown 保留、审计成功/失败、fallback 独立记录和无内容回显；canary 必须离线可重复。测量最大合法 prompt/query 下 policy + audit p95，并验证审计数据库故障时 0 次 provider egress。

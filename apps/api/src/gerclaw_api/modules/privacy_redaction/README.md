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
Next.js TTS BFF, model prompts, exports, AgentScope internal search and a
user-facing processing ledger still require their own purpose-specific adapters
before they can claim unified coverage.

Before every AgentScope model-provider attempt, `FailoverChatModel` also creates
an in-memory, provider-bound copy of every message and applies the distinct
`external_model_prompt` `1.0.0` projection to each nonblank string field. This preserves
message and tool-block structure while removing identifiers and credentials;
oversized values fail closed. The local Agent state, encrypted history and
document store are not mutated. Model-prompt egress decisions are not yet
persisted in `provider_egress_events`, so this projection must not be described
as a complete model-provider audit ledger or as consent management.

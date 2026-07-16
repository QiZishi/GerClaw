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
de-identified, safe to send, or consented. The legacy Next.js TTS BFF, MinerU,
model prompts, exports, AgentScope internal search and a user-facing processing
ledger still require their own purpose-specific adapters before they can claim
unified coverage.

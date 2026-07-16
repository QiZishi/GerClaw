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

Current scope is external online-search query and FastAPI TTS egress. FastAPI
TTS writes an internal, PHI-free `prepared → succeeded|failed` provider record
before/after egress; it contains only purpose, processor, policy version and
per-field category counts. ASR audio, the legacy Next.js TTS BFF, MinerU,
model prompts, exports, search-provider ledger records and a user-facing
processing ledger require their own purpose-specific adapters before they can
claim unified coverage.

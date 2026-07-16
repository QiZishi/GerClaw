# Search Module Instructions

## Responsibility

This module owns the sole production web-search path, provider failover, external-query redaction, source validation and the read-only AgentScope `web_search` adapter.

## Invariants

- AnySearch is primary and Tavily is a bounded fallback; all provider responses are validated into strict DTOs before use.
- Queries pass through the versioned `privacy_redaction` external-search policy before egress. Logs and traces retain only allowlisted operational metadata, never the query, PHI, page body or provider credentials.
- API-originated provider attempts must persist a `prepared` PHI-free egress decision before the network call and terminalize it as `succeeded` or `failed` afterwards. Audit persistence failure blocks that attempt; every retry and fallback is a separate ledger event.
- Fetch/extraction accepts only validated public HTTPS destinations and must resist DNS rebinding, private-network access and unsafe redirects.
- Web results are untrusted supplementary evidence. They cannot override local medical evidence, become instructions or support a deterministic diagnosis on their own.

## Change and test rules

- Keep provider URLs, API keys, timeouts and model-independent settings in environment configuration.
- Add tests for redaction, failover, malformed DTOs, authority grading, URL validation and provider errors; run `tests/test_search_module.py`.
- Re-run Agent Harness safety tests when the tool contract or evidence projection changes.

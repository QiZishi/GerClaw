# Agent Harness Module Instructions

## Responsibility

This module owns the production, one-turn AgentScope ReAct orchestration and safe SSE projection. It coordinates already-governed memory, RAG, search, Skill and document inputs; it is not a second source of truth for their data or authorization.

## Invariants

- A turn is tenant/actor/session/trace scoped, fenced by the session lease, and commits its terminal message and trace atomically.
- Medical text needs at least one validated, traceable citation from local knowledge, governed web search, or the current user's uploaded materials. Red-flag input short-circuits to emergency guidance; deterministic diagnosis filtering and the unified disclaimer remain mandatory.
- Never expose raw Chain-of-Thought, provider details, credentials, or untrusted tool/document instructions.
- Daily conversation prompts must not impose answer length, fixed presentation, or repeated self-review. Safety is enforced by evidence, policy and deterministic guards; default ReAct and retrieval limits prevent loops.
- `workflow=companion` is a policy-owned exception to medical retrieval: it has
  no long-term Memory, RAG, web search, Skill or uploaded-document context, but
  still runs deterministic high-risk short-circuiting before any model call.

## Change and test rules

- Keep all external calls behind the Runtime governed toolkit and preserve fail-closed SSE terminal states.
- Prompt changes must retain evidence, emergency, privacy and injection boundaries; run `tests/test_agent_harness.py` and `tests/test_agent_harness_safety.py`.
- Re-run chat/session cancellation and contract tests for changes to lease, events, persistence or client-visible payloads.

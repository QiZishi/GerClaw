# Companion

`companion` supplies the policy for the `workflow=companion` Chat mode. The
mode reuses the production Chat transaction, SSE, tenant/actor/session
isolation and deterministic red-flag safety checks, while removing long-term
health Memory, RAG, web search, Skills and uploaded documents from the model
context.

It is deliberately a limited backend baseline: a supportive AI may listen and
respond respectfully, but cannot present itself as human, promise to remain or
contact someone, create dependency, make clinical conclusions or substitute
for professional or emergency support. The existing red-flag short-circuit
remains authoritative. A user-configurable companion-memory preference,
human escalation and doctor authorization are not implemented.

## Patient entry

The patient welcome page exposes **暖心陪伴**. Entering it starts a fresh local
conversation and sends `workflow=companion` with empty Skill and document
lists. The UI hides image, document and Skill controls and explains that only
the current conversation is used. This is defense in depth; the API contract
still rejects non-empty Skill or upload context.

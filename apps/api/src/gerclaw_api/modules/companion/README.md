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
frontend entry, human escalation and doctor authorization are not implemented.

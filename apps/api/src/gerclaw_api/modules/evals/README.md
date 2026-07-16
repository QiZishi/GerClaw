# Eval baseline module

This module starts the safe, deterministic portion of GerClaw's Eval Harness.
It executes reviewed synthetic safety cases against the same red-flag detector,
safety-decision contract, emergency public-output invariant, and deterministic
medical-output rewrite used by the Agent Harness. It has no database, model,
RAG, search, or provider dependency. The CLI emits only IDs and outcomes, never
the reviewed synthetic input or expected public text.

Run:

```bash
cd apps/api
uv run python -m gerclaw_api.modules.evals.cli
```

Bad Case records remain encrypted and tenant-scoped. They are not replayed
directly. A future authorised reviewer must create a new de-identified,
synthetic canonical case before it may be added here. This baseline therefore
does not expose user data or claim to evaluate LLM quality, medical validity,
retrieval quality, or capacity.

`run_opt_in_rag_retrieval_evaluation` is a separate, asynchronous path for a
reviewed synthetic RAG case set. It has no built-in cases: a reviewer must bind
every synthetic query to expected local-corpus document IDs and one index
version. The caller must pass `allow_external_rag=True`, an index version, a
top-k value and a maximum case budget. Its report contains IDs, counts and
outcomes only; it never emits queries, retrieved text, source paths or model
content. It is an evidence-retrieval regression check, not a medical-validity
or model-quality claim.

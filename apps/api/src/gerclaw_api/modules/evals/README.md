# Eval baseline module

This module starts the safe, deterministic portion of GerClaw's Eval Harness.
It executes reviewed synthetic safety cases against the same red-flag detector,
safety-decision contract, and emergency public-output invariant used by the
Agent Harness. It has no database, model, RAG, search, or provider dependency.

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

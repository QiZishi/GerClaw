# Eval baseline module

This module starts the safe, deterministic portion of GerClaw's Eval Harness.
It executes reviewed synthetic safety cases against the same red-flag detector,
safety-decision contract, emergency public-output invariant, and deterministic
medical-output rewrite used by the Agent Harness. It has no database, model,
RAG, search, or provider dependency. The CLI emits only IDs and outcomes, never
the reviewed synthetic input or expected public text.

The same command also runs committed `privacy-redaction-case-v1` canaries for
the server-owned `1.1.0` external-search and TTS policies. Their output contains
only a case ID, purpose, policy version and PHI-free category counts; it never
contains source text, expected redacted text, matching spans or credentials.
They are deterministic text-policy regression checks only. They do not measure
OCR, ASR, free-form structured fields, model-based detection, false-positive or
false-negative production rates, and therefore do not prove full PHI coverage.

`medication-rule-case-v1` adds six reviewed, synthetic cases that bind
`medication-rules-v3` findings to exact rule IDs and local source IDs. The
result never emits a medication list, patient attribute, rule text or source
content. It guards deterministic wiring and provenance only; it is not a
complete DDI/Beers/dose evaluation or clinical-validity evidence.

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
reviewed synthetic RAG case set. The committed
`evals/rag-retrieval-reviewed-v1.json` currently contains five version-bound,
source-checked positive retrieval baselines spanning polypharmacy, falls,
frailty, cognition and stable coronary medication management, plus one
no-evidence baseline. It contains no patient or provider content. A reviewer
must still bind every new synthetic query to its expected local-corpus document
IDs (or explicitly require no evidence) and one index version; duplicate case
IDs are rejected. A positive case also rejects every returned result whose
citation provenance cannot locate its chunk (document ID, chunk ID, title,
chapter, category, source type and bounded chunk position); a reviewed case
may further require specific source types. The caller must pass
`allow_external_rag=True`, an index version, a top-k value and a maximum case
budget. Its report contains IDs, counts and outcomes only; it never emits
queries, retrieved text, source paths or model content. It is an
evidence-retrieval regression check, not a medical-validity or model-quality
claim.

For a real, cost-bearing run use the separate CLI, which refuses to execute
without an explicit opt-in:

```bash
cd apps/api
uv run gerclaw-eval-rag \
  --allow-external-rag \
  --cases evals/rag-retrieval-reviewed-v1.json \
  --index-version markdown-heading-v1:lexical-cjk-ngram-v1:BAAI/bge-m3:1024 \
  --top-k 5 --max-cases 6
```

The case file must be a `rag-retrieval-case-set-v1` JSON object with only
reviewed synthetic `RAGRetrievalEvalCase` entries. New corpus-specific expected
document IDs still require a reviewer to confirm the intended source and index
version first.

# Eval Module Instructions

## Responsibility

This module owns versioned, reviewed, synthetic regression cases and
deterministic runners. It is the safe destination for a Bad Case only after a
reviewer has removed identifiers, free text, patient facts, and provider
content and has written a new canonical case.

## Invariants

- Never copy a `BadCase`, `Trace`, feedback comment, raw prompt, user message,
  model output, attachment, document text, or identifier into a golden case.
- Every case has a schema version, policy/version expectation, bounded
  synthetic input, and deterministic pass/fail condition.
- Safety baselines must not call LLM, RAG, search, tools, or external
  providers. External evaluations require a separately explicit opt-in and
  must record their budget and nondeterminism.
- Privacy-policy canaries may use only reviewed synthetic input and may report
  a purpose, policy version and PHI-free category counts. They must never emit
  source text, expected redacted text, matched spans, replacement positions or
  credentials.
- A passing policy baseline does not prove clinical correctness, model quality,
  RAG quality, or capacity. Preserve the exact claim boundary in reports.
- Medication-rule canaries bind a synthetic list only to expected rule/source
  IDs and ruleset version. Results must never expose the list, patient data,
  source content or a patient-executable recommendation.
- Skill-draft canaries bind synthetic instructions only to deterministic
  checklist codes and `skill-draft-quality-v1`. Results must never expose the
  instructions, a user request, model output, or imply medical validity or
  automatic publication.
- Memory-extraction canaries exercise the production evidence guards with
  reviewed synthetic input and in-memory synthetic structured output only.
  Results may expose category/status/action but must never expose input,
  entity, statement, evidence span, candidate details, or model content.

## Change and test rules

- Add a test for normal, negative, malformed, and regression conditions when
  changing case contracts or runners.
- Run `uv run python -m gerclaw_api.modules.evals.cli` and the targeted pytest
  file. Keep outputs PHI-free and stable enough for CI comparison.

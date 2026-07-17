# Validation module

## Responsibility

Own versioned, fail-closed schemas for data crossing module and public transport
boundaries. It does not replace domain models or business/medical policy.

## Invariants

- Validate at the producing boundary and again immediately before public SSE.
- Schemas reject unknown fields unless a separately versioned compatibility rule
  explicitly allows them.
- Validation errors are bounded messages; they must never include source
  payloads, PHI, provider output, secrets or hidden reasoning.
- `local-rag-evidence-v1` is required at the Hybrid RAG producer and must be
  reused by the AgentScope adapter, citation projection and RAG evals; invalid
  provenance may not be repaired with fallback location fields.
- Versioned structured-model projections use
  `validate_versioned_model_output*`; their domain schema must expose a
  literal `model_output_schema_version`, and a mismatch may not be repaired
  into a different contract.
- Add a contract test for every event/schema change and update the frontend Zod
  consumer in the same change when the public payload changes.

## Dependency direction

May depend on Pydantic and shared public contracts. It may not call databases,
providers, AgentScope, tools, repositories or HTTP routes.

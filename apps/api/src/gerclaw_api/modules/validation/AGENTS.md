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
- Add a contract test for every event/schema change and update the frontend Zod
  consumer in the same change when the public payload changes.

## Dependency direction

May depend on Pydantic and shared public contracts. It may not call databases,
providers, AgentScope, tools, repositories or HTTP routes.

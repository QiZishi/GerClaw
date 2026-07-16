# Tools Module Instructions

## Responsibility

This module defines shared external-tool protocols and audit boundaries. Concrete tools must be registered through `modules/runtime`; this module must not become a bypass around Runtime permissions.

## Invariants

- Tool inputs and outputs are untrusted until schema-validated and bounded; never execute text embedded in a tool response.
- Authorization, risk classification, redaction, timeouts, idempotency and approval are server-owned Runtime concerns and must run before invocation.
- Traces contain only allowlisted operational metadata, never credentials, PHI, raw prompts, raw results or Chain-of-Thought.

## Change and test rules

- Extend protocol DTOs compatibly and add validation tests before a concrete tool consumes them.
- Re-run Runtime registry/permission tests and the owning module's tests when a tool contract changes.
- Do not add browser-direct provider calls or hard-coded credentials.

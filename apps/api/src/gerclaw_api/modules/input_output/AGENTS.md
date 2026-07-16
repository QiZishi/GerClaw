# Input / Output Module Instructions

## Responsibility

This module owns shared, typed boundaries for text, attachment and voice input plus safety-reviewed output rendering contracts. It is a boundary layer, not a provider implementation or clinical decision engine.

## Invariants

- Validate every untrusted input before it reaches a model, storage, tool or provider; preserve declared size, MIME and schema limits.
- Output rendering must preserve medical safety notices and never leak raw provider errors, secrets, Chain-of-Thought or unvalidated content.
- Contracts are versioned shared interfaces: do not silently change a required field, default or error code consumed by routes or the MVP BFF.

## Change and test rules

- Add boundary tests for malformed payloads, maximum sizes, cancellation and stable error projection.
- Run `tests/test_io_tool_contracts.py` and the route/client contract tests affected by any protocol change.
- Keep provider credentials and provider-specific parsing outside this module.

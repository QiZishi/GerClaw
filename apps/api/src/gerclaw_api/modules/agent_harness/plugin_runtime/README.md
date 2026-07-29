# Plugin Runtime

This package currently defines `PluginManifest`, `CapabilityResult`, and the injection
Protocol. It does not activate a second plugin system; existing GerClaw modules remain the
only capability owners.

Unknown capabilities and invalid payloads must fail before execution. Stage 4 registers CGA,
medication review, five-prescription, and report capabilities and adds shared parsing/search
results. Measure success with allowlist coverage, zero duplicate input processing, and equal
manual/automatic governance.

Consumers: future planner and user capability selection. Configuration: allowlisted manifests
and budgets are injected at composition. Known limit: no manifest is registered or invoked by
this package yet. Acceptance: unknown IDs fail, schemas validate at both boundaries, and
shared result references stay actor/session scoped.

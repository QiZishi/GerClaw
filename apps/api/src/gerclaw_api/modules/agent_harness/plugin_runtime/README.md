# Plugin Runtime

This package defines `PluginManifest`, `CapabilityResult`, and the injection Protocol. Its
production adapter builds the existing governed Runtime registry for local RAG, Memory, and
web search tools; `TurnToolkit` composes the owner-provided AgentScope adapters, while
`ApprovalCoordinator` validates and durably parks AgentScope ASK requests. It does not
activate a second plugin system, and existing GerClaw modules remain the only capability
owners.

Unknown capabilities and invalid payloads must fail before execution. Stage 4 registers CGA,
medication review, five-prescription, and report capabilities and adds shared parsing/search
results. Measure success with allowlist coverage, zero duplicate input processing, and equal
manual/automatic governance.

Consumers: the current composition entry, future planner, and user capability selection.
Configuration: Runtime principal, approval callback/TTL, allowlisted manifests, and budgets are
injected at composition. Known limit: clinical capability manifests are not registered or
invoked by this package yet. Acceptance: tool inputs fail before execution when invalid,
approval requests are durably parked, unknown IDs fail, and shared result references stay
actor/session scoped.

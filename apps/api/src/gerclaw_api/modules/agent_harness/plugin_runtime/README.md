# Plugin Runtime

This package defines the versioned capability allowlist and its request-local composition
boundary. `GovernedCapabilityCatalog` registers the existing CGA, medication review,
five-prescription, and Run Artifact owners. Manual, workflow, and deterministic automatic
selection all resolve through the same allowlist; selection never imports or invokes arbitrary
Python. `GET /api/v1/capabilities` exposes the content-free manifest directory to account and
guest workspaces through a strict Pydantic/Zod contract.

The production adapter continues to build the Runtime-owned registry for local RAG, Memory,
and web search tools. `TurnToolkit` composes the owner-provided AgentScope adapters, while
`ApprovalCoordinator` validates and durably parks AgentScope ASK requests. Successful
AgentScope Skill results now complete the matching optional DynamicPlan checkpoint; an unknown,
failed, or repeated Skill result cannot do so.

`TurnSharedResultStore` and `TurnResultReuse` hold authorized attachment projections, reduced
clinical observations, and local retrieval results once per
`tenant + actor + session + trace`. References are opaque and consumer-allowlisted; private
payloads never enter the reference or a public event. A tolerated RAG outage emits exactly one
failed terminal tool event and cannot be relabelled as success.

Consumers: ChatService planning, the production Harness, the capability directory client, and
the existing owner flows. Configuration: Runtime principal, approval callback/TTL, manifests,
and budgets are injected at composition. Failure semantics: unknown/duplicate capabilities,
unsupported workflow selection, scope mismatch, consumer denial, and reuse-key contract drift
fail closed with stable codes.

Known limit: a manifest is a governed entrypoint descriptor, not a generic invocation API.
CGA scoring, medication review, five-prescription generation, and Artifact persistence must
still execute through their existing typed owner state machines. Stage 5 connects these
entrypoints to the unified workspace. Measure success with full allowlist coverage, one
retrieval/attachment projection per turn, exact single terminal events, and identical policy
for manual and automatic selection.

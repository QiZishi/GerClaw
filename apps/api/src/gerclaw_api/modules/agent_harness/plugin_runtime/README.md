# Plugin Runtime

This package defines the versioned capability allowlist and its request-local composition
boundary. `GovernedCapabilityCatalog` registers the existing CGA, medication review,
five-prescription, and Run Artifact owners. Manual, workflow, and deterministic automatic
selection all resolve through the same allowlist; selection never imports or invokes arbitrary
Python. `GET /api/v1/capabilities` exposes the content-free manifest directory to account and
guest workspaces through a strict Pydantic/Zod contract. `ChatRequest.requested_capabilities`
provides the same allowlisted manual path used by workflow and automatic selection.

The production adapter continues to build the Runtime-owned registry for local RAG, Memory,
and web search tools. `TurnToolkit` composes the owner-provided AgentScope adapters, while
`ApprovalCoordinator` validates and durably parks AgentScope ASK requests. Successful
AgentScope Skill results now complete the matching optional DynamicPlan checkpoint; an unknown,
failed, or repeated Skill result cannot do so.

Tool capacity admission is injected as a Protocol callback but executed by the Runtime-owned
proxy only after schema validation and a fresh `ALLOW` permit, immediately before the real
delegate. `DENY`/`ASK` paths never run this callback. The callback receives the validated full
arguments and immutable capability ceiling; Plugin Runtime does not guess from partial stream
deltas or duplicate Runtime authorization.

`GovernedCapabilityRuntime` validates a content-free owner scope and dispatches every selected
manifest to its exact injected owner entrypoint. Production connects CGA to its resumable
assessment workspace, medication review and five-prescription to their idempotent typed
intakes, and report requests to the actor-owned Artifact workspace. Successful owner results
complete the matching optional plan checkpoint; missing owners, invalid input, or mismatched
owner results fail closed. The runtime does not copy scoring, intake, draft, or persistence
logic into the Harness.

Manifest `input_schema` and `output_schema` are the public JSON Schema projections of the exact
strict Pydantic owner-adapter contracts. Runtime construction and every invocation reject a
manifest whose declared schemas drift from those executable contracts. The input is validated
before owner dispatch and the returned value is validated again before its public summary or
opaque reference can cross the boundary; unknown fields fail closed with bounded, content-free
error codes. Capability-specific clinical state remains in its existing owner and repository,
not in a parallel Harness payload.

`TurnSharedResultStore` and `TurnResultReuse` hold authorized attachment projections, reduced
clinical observations, and local retrieval results once per
`tenant + actor + session + trace`. References are opaque and consumer-allowlisted; private
payloads never enter the reference or a public event. A tolerated RAG outage emits exactly one
failed terminal tool event and cannot be relabelled as success.

Consumers: ChatService planning, the production Harness, the capability directory client, and
the existing owner flows. Configuration: Runtime principal, approval callback/TTL, manifests,
and budgets are injected at composition. Failure semantics: unknown/duplicate capabilities,
unsupported workflow selection, manifest schema drift, invalid owner input/output, scope
mismatch, consumer denial, and reuse-key contract drift fail closed with stable codes.

Known limit: chat activation connects the existing owner workspace but does not bypass its
required user-input or clinical-review state transitions. Stage 5 adds the visible manual
workspace controls and editable Artifact experience. Measure success with full allowlist coverage, one
retrieval/attachment projection per turn, exact single terminal events, and identical policy
for manual and automatic selection.

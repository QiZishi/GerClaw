# Routing

The package defines the versioned construction boundary, route vocabulary, injected
`RoutingPolicy`, and production `DeterministicRouter`. Emergency always wins. Multiple
capabilities, multiple attachments, explicitly complex deliverables, and large requests select
Deep; ordinary medical/attachment work selects Standard; only short non-medical requests
without attachments or capabilities select Quick.

Invalid input fails before model execution. Emergency decisions set `model_allowed=false` and
skip Skill resolution/session mutation, Memory construction/recall/compression, conversation
context hydration, and uploaded-document resolution before the deterministic notice is emitted;
Quick disables the turn tool registry, so it cannot call RAG, Memory, Search, Skill, or a
complex planner. Thresholds are resolved from `Settings` into `ResolvedHarnessConfig`; this
package reads no environment.

Consumers: `ChatService` persists the decision on `AgentRun`, and the Harness enforces the same
decision before any model call. Failure semantics: invalid contracts fail closed; Emergency
emits the existing deterministic 120/急诊 notice and unique terminal response. Known limit:
route selection governs orchestration cost and safety, not clinical validity. Acceptance:
deterministic fixture results, zero model calls before red-flag output, and zero tool calls for
Quick.

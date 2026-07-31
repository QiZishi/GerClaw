# Context Snapshot Instructions

Owns the immutable, bounded input contract for one Agent turn and the encrypted-at-rest
resume material required to continue that same Run. It does not fetch Memory, documents,
conversation rows, profiles, or current Skill content.

Every field crossing into the Harness must be actor/tenant scoped and validated before
construction. Never add raw credentials, provider payloads, unrestricted PHI, private
reasoning, or unbounded history. Unknown and absent data must remain distinguishable.

## Core mechanism that must not be changed

- A snapshot is a frozen, point-in-time view. Resume must consume it and must not silently
  rebuild history, Profile, Memory references, ClinicalState, Skill definitions, parsed
  documents, route, plan, or budgets from their current mutable state.
- Content owners remain Conversation, Memory, ClinicalState, Skill, Document, Planning, and
  Runtime. This component validates and freezes their already authorized outputs; it never
  becomes their CRUD owner.
- `PersistedContextSnapshot` is encrypted PHI-bearing state. Public Run/Event APIs must never
  return it, and evolution signals must never copy its content.
- Current authorization is always re-evaluated on resume. A frozen snapshot is not a frozen
  permission grant.
- Unknown, absent, negative, and conflicted clinical facts remain distinct.
- Schema or identity mismatch fails closed with a stable resume-data error; it must never
  fall back to "use whatever is current".
- Context capacity is decided before a model side effect from a complete, content-free
  inventory. Current input, safety policy, ClinicalState, tool contracts, selected Skill
  versions, plan, document projection, image cost, and evidence/output reserves are required
  inputs. Only conversation history and its prior summary are compressible.
- Capacity uses injected dual thresholds with `reserve < soft trigger < hard stop < 1`.
  Crossing soft compresses history; crossing hard with required inputs fails before a
  Provider side effect. Never copy a Codex-private ratio into GerClaw.
- Emergency is a deterministic pre-model safety short-circuit. Context accounting must never
  turn a model-window overflow into a blocker for its 120/emergency-care response.
- Compression must preserve recent turns verbatim and retain clinically critical user
  excerpts without converting them into diagnoses. A model compression failure must use the
  deterministic extractive fallback, never silently drop all history or fabricate a summary.
- Successful Provider compression is not proof of retention. Profile/Memory projections,
  ClinicalState/decision, admitted documents/evidence, runtime user directives, output repair
  instructions, and the newest user turn must be withheld from the compressible set and
  verified in code after compression.
- AgentScope compresses before its public model-start event. Capacity admission must wrap the
  actual request-scoped compression entry; an event observer is audit timing, not a pre-model
  gate. Concurrency-safe tools must be admitted as one complete batch before any owner side
  effect, with one combined result reserve and no shared temporary-marker race.
- Hard admission must account for AgentScope's actual prepared Provider input: dynamic system
  prompt, summary, every content-block kind, and activated tool schemas. A local complete
  projection is the availability-preserving fallback when the read-only token counter fails.
- Compression cancellation and failure restore summary/context atomically. Retained lineage
  keeps the source identity captured before compression, including exact duplicate messages;
  never infer retained identity by renumbering the after-projection occurrence.
- `source_hash`, strategy, before/after estimates, source budgets, and retained message counts
  are frozen. New Runs use `context-projection-v2`, including stable retained/omitted source
  IDs, source range, summary hash lineage, and opaque unresolved-item IDs. Resume accepts and
  reuses frozen v1 or v2 without silently rebuilding it.

Consumers may depend on these models; this package depends only on public domain contracts.
Run context, Harness, Chat, and recovery tests after changes.

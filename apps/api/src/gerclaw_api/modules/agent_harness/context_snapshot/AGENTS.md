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

Consumers may depend on these models; this package depends only on public domain contracts.
Run context, Harness, Chat, and recovery tests after changes.

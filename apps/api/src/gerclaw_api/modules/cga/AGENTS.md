# CGA Module Instructions

## Responsibility

This module owns versioned, deterministic screening-scale definitions and scoring only. PHQ-9, SAS, score-bearing PSQI, Mini-Cog and MMSE have server workflows. Mini-Cog and MMSE accept only the participant's bounded self-report values: the system must never claim that a drawing, movement, writing, reading, or spoken answer was machine- or clinician-verified. PSQI item 5J may additionally retain an optional, encrypted free-text note; it never changes scoring and is not included in public reports, history or export. The service layer owns the authenticated, persisted state machine; routes own HTTP concerns.

## Invariants

- A client may submit only a server-provided current `question_id` and an option value defined by that scale.  Never accept client-supplied wording, score totals, severity, or report content.
- Screening is not diagnosis.  Every report must retain a medical disclaimer.  PHQ-9 item 9 safety handling must remain distinct from aggregate-score follow-up.
- Start, answer and complete writes create an atomic Runtime Trace containing only scale/version, operation, answer count and status. Never add question IDs, scores, risk flags, notes, assessment IDs or raw request bodies to that Trace.
- Scale source, item order, option values, reverse scoring, thresholds, and definition version are immutable facts.  Add a new version rather than silently changing a published definition.
- Historical comparison may use only the caller's immediately prior completed record for the same scale. It must refuse a changed definition version and may expose a numerical delta with a screening disclaimer, never a clinical interpretation of direction.
- This module must not call LLMs, RAG, web search, TTS, or external clinical services.

## Change and test rules

- Add a dedicated scoring module and boundary tests for every new scale, including malformed/missing answers and threshold edges.
- Extend the server state machine, encrypted persistence constraint, Pydantic/Zod contracts, migration, and an API exercise before exposing a scale in UI.
- Preserve backward readability for persisted reports when response contracts add required fields.

# CGA Module Instructions

## Responsibility

This module owns versioned, deterministic screening-scale definitions and scoring only.  PHQ-9 and SAS have complete server workflows; PSQI currently has a tested scoring core only and must not be exposed until the mixed time/duration input contract is implemented.  The service layer owns the authenticated, persisted state machine; routes own HTTP concerns.

## Invariants

- A client may submit only a server-provided current `question_id` and an option value defined by that scale.  Never accept client-supplied wording, score totals, severity, or report content.
- Screening is not diagnosis.  Every report must retain a medical disclaimer.  PHQ-9 item 9 safety handling must remain distinct from aggregate-score follow-up.
- Scale source, item order, option values, reverse scoring, thresholds, and definition version are immutable facts.  Add a new version rather than silently changing a published definition.
- This module must not call LLMs, RAG, web search, TTS, or external clinical services.

## Change and test rules

- Add a dedicated scoring module and boundary tests for every new scale, including malformed/missing answers and threshold edges.
- Extend the server state machine, encrypted persistence constraint, Pydantic/Zod contracts, migration, and an API exercise before exposing a scale in UI.
- Preserve backward readability for persisted reports when response contracts add required fields.

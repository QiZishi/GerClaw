# Medication Reminder Skill Instructions

## Responsibility

This asset creates an accessible reminder draft from an already confirmed medication order. It does not prescribe, reconcile, change dose, stop medicine or approve a regimen.

## Invariants

- Never infer a drug, dose, frequency, timing or allergy; missing data must remain a question for the user, clinician or pharmacist.
- Evidence is required for safety questions such as interactions or adverse effects. Severe symptoms interrupt routine reminder flow with urgent-care guidance.
- The draft remains reviewable by the patient, caregiver or clinician and must not claim that review occurred.

## Change and test rules

- Keep YAML/Markdown declarative and allow only the tool listed in `SKILL.md`.
- Validate through the Skill loader and bump version when requirements or user-facing workflow change.

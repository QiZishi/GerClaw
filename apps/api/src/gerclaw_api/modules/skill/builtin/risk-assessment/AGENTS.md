# Risk Assessment Skill Instructions

## Responsibility

This asset supports evidence-based conversational screening for selected geriatric risks. It is not a diagnosis engine and must not replace the deterministic CGA module when a server-supported scale is available.

## Invariants

- Confirm applicability and retrieve the current local evidence before presenting a scale item, scoring rule or threshold.
- Keep questions understandable and allow uncertainty or refusal. Insufficient data remains pending professional assessment.
- Acute red flags end screening immediately and route to urgent care; no screening label may be presented as a definitive diagnosis.

## Change and test rules

- Keep the workflow declarative, use only declared tools and do not duplicate deterministic server scale definitions.
- Validate through the Skill loader and version every behavioral change.

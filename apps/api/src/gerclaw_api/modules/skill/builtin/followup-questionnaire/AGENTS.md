# Follow-up Questionnaire Skill Instructions

## Responsibility

This asset defines a clinician-editable follow-up questionnaire draft for older patients. It gathers follow-up information; it does not diagnose, score a condition or issue treatment orders.

## Invariants

- Separate user self-report from clinician conclusions and obtain local evidence before using a scale, threshold or medical claim.
- Ask only information relevant to the stated follow-up goal. Red flags must route to urgent care rather than continue routine questioning.
- Keep the result editable and source-marked; do not impose arbitrary answer length or simulate clinician approval.

## Change and test rules

- Maintain declarative YAML/Markdown only and use only declared allowlisted tools.
- Validate this asset through the Skill loader and update its version when behavior changes.

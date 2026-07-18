# Medication review

This module stores medication-review inputs through the encrypted clinical-intake service and provides two separate outputs:

- `GET /api/v1/clinical-intakes/{id}/medication-reconciliation` is a non-clinical preview of only Unicode/whitespace-equivalent list rows.
- `POST /api/v1/clinical-intakes/{id}/medication-review-draft` creates and encrypts a deterministic, clinician-review-only artifact from the installed source-traceable rule set. `GET /api/v1/clinical-intakes/{id}/medication-review-drafts` returns at most 20 newest-first revisions for the same tenant/actor and intake. Each revision is bound to the source ruleset and the exact intake revision used to generate it. No LLM, RAG, web search, or external medication provider receives the list.

`rules/core-v1.json` currently carries `medication-rules-v3`: 30 exact DDI rules, four exact daily-dose thresholds, duplicate/polypharmacy review, and one age-qualified benzodiazepine signal. The installed DDI rules cover locally sourced statin, nitrate/PDE5 inhibitor, antiplatelet/PPI, digoxin, beta-blocker/calcium-channel blocker, and selected metabolic drug pairs. The four source records carry a locator and source-file SHA-256, so a reviewer can verify the exact corpus version. Results are concrete, evidence-bound rule-hit conclusions for clinician/pharmacist review; they are not a diagnosis and do not imply that an unreviewed non-match is safe.

Contraindicated and major findings additionally create an owner-scoped fixed
safety alert in the same database transaction. The alert deliberately omits
drug names, doses, rule text and source locators; it only directs the person to
urgent clinician/pharmacist review and does not authorise self-adjustment.

Beers-related coverage is reported as `limited_source_traceable`, not as a full Beers implementation. The system does not turn a non-match into “no finding” or “safe”; expanding coverage requires a permitted versioned dataset and clinical governance review. Medication-review intake accepts no document references, because five-prescription uploads have a distinct owner/session-scoped MinerU input boundary.

医生端直接呈现具体结论、条件与来源；患者端仅在结果末尾显示一次风险提示。历史结果不是当前输入的替代品：若信息收集 revision 已变化，界面必须提示重新审查。

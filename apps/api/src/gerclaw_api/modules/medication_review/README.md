# Medication review

This module stores medication-review inputs through the encrypted clinical-intake service and provides two separate outputs:

- `GET /api/v1/clinical-intakes/{id}/medication-reconciliation` is a non-clinical preview of only Unicode/whitespace-equivalent list rows.
- `POST /api/v1/clinical-intakes/{id}/medication-review-draft` creates and encrypts a deterministic, clinician-review-only artifact from the installed source-traceable rule set. `GET /api/v1/clinical-intakes/{id}/medication-review-drafts` returns at most 20 newest-first revisions for the same tenant/actor and intake. Each revision is bound to the source ruleset and the exact intake revision used to generate it. No LLM, RAG, web search, or external medication provider receives the list.

`rules/core-v1.json` currently carries `medication-rules-v4`: 30 exact DDI rules, four exact daily-dose thresholds, duplicate/polypharmacy review, and one age-qualified benzodiazepine signal. The installed DDI rules cover locally sourced statin, nitrate/PDE5 inhibitor, antiplatelet/PPI, digoxin, beta-blocker/calcium-channel blocker, and selected metabolic drug pairs. The four source records carry a locator and source-file SHA-256, so a reviewer can verify the exact corpus version. Results are concrete, evidence-bound rule-hit conclusions for clinician/pharmacist review; they are not a diagnosis and do not imply that an unreviewed non-match is safe.

Contraindicated and major findings additionally create an owner-scoped fixed
safety alert in the same database transaction. The alert deliberately omits
drug names, doses, rule text and source locators; it only directs the person to
urgent clinician/pharmacist review and does not itself constitute a treatment order.

Beers-related coverage is reported as `limited_source_traceable`, not as a full Beers implementation. The system does not turn a non-match into “no finding” or “safe”; expanding coverage requires a permitted versioned dataset and clinical governance review. Medication-review intake accepts no document references, because five-prescription uploads have a distinct owner/session-scoped MinerU input boundary.

医生端直接呈现具体结论、条件与来源；患者端仅在结果末尾显示一次风险提示。历史结果不是当前输入的替代品：若信息收集 revision 已变化，界面必须提示重新审查。

登录患者可把 `medication_review_read` 授予一名指定医生。该授权让医生读取
加密保存的审查记录、输入版本和规则来源，并为该 artifact 追加自己的
`approved`/`returned` 复核意见；意见加密保存、绑定 artifact 内容 SHA-256，
按医生单调递增 revision，不能覆盖原审查或触发治疗执行。不会开放会话、Trace、
原始附件或其他健康资料。医生可在“患者列表”中直接打开已授权记录，或按
患者代码读取；撤回、到期和未知患者均返回相同的不可见结果。

## 维护与演进

**可安全改进。** 可在获得许可、来源版本、临床审核人与复审日期后扩充 DDI/剂量/Beers 数据；新规则必须有精确 match 语义、source locator、合成 case 与明确的适用/未知状态。可完善医生审核/发布工作台，但不能把有限规则伪装为完整审查。

**不可破坏的契约。** `medication-rules-v4` 的 finding 必须绑定本地来源和 intake revision；非命中不等于安全，未知药物不能制造阴性结论。禁忌/严重命中写 alert 与审查 artifact 必须同事务；医生只能在活动授权后读取 artifact 并追加本人不可覆盖的复核记录，不含会话、Trace、附件或其他健康记录，也不能修改 artifact 或执行治疗。

**性能与回归验收。** 每条新增规则需有命中、边界、未知/不匹配和来源指纹回归；必测 artifact 刷新恢复、输入 revision 变化、授权撤回、跨主体拒绝，以及同一医生连续复核 revision 递增/内容不可覆盖。10 个独立 intake 并发审查必须 10/10 有唯一 Trace/来源绑定 finding；规则计算 p95 与加密持久化 p95 分开报告。

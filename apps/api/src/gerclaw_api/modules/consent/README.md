# Patient access consent

`consent` provides a narrow, patient-controlled read-authorisation primitive.
Each grant names one doctor account, one protected resource and an expiry. The
patient may renew or revoke it using the returned revision. It does not prove a
doctor licence or permit clinical writes, prescriptions, approvals, emergency
override, chat/Trace/document access, or access to uncompleted CGA answers.
`prescription_draft_review` additionally permits that named doctor to read
the patient's generated review-only five-prescription drafts and append a
clinician review. It never turns the draft into an executable prescription.
`medication_review_read` permits only the persisted, source-bound medication
review artifact: its input revision, deterministic findings and rule sources.
It is read-only and never discloses the chat, Trace, uploaded materials or
other patient records.

The production consumer must call `SqlAlchemyPatientAccessGrantRepository`
immediately before reading a protected patient resource. A failed lookup is
deliberately indistinguishable from an unknown patient to the doctor.

The API emits only opaque account IDs, resource scope, status, revision and
timestamps. Health data never enters the grant, audit or error payload.

## 维护与演进

**可安全改进。** 可增加经产品和临床治理批准的新只读 resource scope、到期提醒和患者目录投影；每个 consumer 必须在读取前实时调用 repository。新增 scope 同步更新 schema、迁移 check constraint、BFF allowlist、医生 UI、撤回测试和对应模块说明。

**不可破坏的契约。** grant 是 patient→指定 doctor→单一资源→期限→revision 的事实源；撤回、过期、tenant/角色不符和未知患者必须 fail closed 且对医生不可区分。不得以 grant 暗示医生资质、紧急访问、写入权或 chat/Trace/附件访问。

**性能与回归验收。** 每个 scope 必测创建、续期、revision 冲突、撤回、到期、跨 tenant/doctor 拒绝及 consumer 的读取前复验；真实浏览器至少覆盖患者授权→医生只读查询→撤回后拒绝。10 并发续期/撤回应保持单一最终 revision，不可短暂过度授权。

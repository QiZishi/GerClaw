# Patient access consent

`consent` provides a narrow, patient-controlled read-authorisation primitive.
Each grant names one doctor account, one protected resource and an expiry. The
patient may renew or revoke it using the returned revision. It does not prove a
doctor licence or permit clinical writes, prescriptions, approvals, emergency
override, chat/Trace/document access, or access to uncompleted CGA answers.
`prescription_draft_review` additionally permits that named doctor to read
the patient's generated review-only five-prescription drafts and append a
clinician review. It never turns the draft into an executable prescription.

The production consumer must call `SqlAlchemyPatientAccessGrantRepository`
immediately before reading a protected patient resource. A failed lookup is
deliberately indistinguishable from an unknown patient to the doctor.

The API emits only opaque account IDs, resource scope, status, revision and
timestamps. Health data never enters the grant, audit or error payload.

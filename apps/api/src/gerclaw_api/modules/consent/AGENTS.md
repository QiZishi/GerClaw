# Consent Module

## Responsibility

Own patient-controlled, time-bounded read grants to a specific active doctor
account. A grant is an access fact, not clinical credential verification,
diagnostic authority, an emergency override, or a permission to mutate data.

## Invariants

- Only a persistent `patient` account may create or revoke its own grants;
  guests, doctors and administrators cannot impersonate a patient.
- Every grant is tenant-scoped, resource-scoped, expiry-bound and revision
  fenced. Expired or revoked records always deny access.
- A doctor may receive only explicitly granted `health_profile_read`,
  `cga_report_read`, `prescription_draft_review` or
  `medication_review_read` or `chronic_care_read`. `chronic_care_read`
  permits only the encrypted, self-reported chronic-condition ledger,
  measurements and non-clinical arithmetic directions; it is read-only and
  never authorises thresholds, interpretation, treatment or mutation. The
  medication scope permits a projection of encrypted,
  source-bound medication-review artifacts and an append-only review record
  for that same doctor only; it never exposes chat turns, Trace, uploaded
  files, raw assessment answers, alerts, approval tokens or emergency access.
  `prescription_draft_review` separately permits append-only review of a
  generated five-prescription draft only; neither scope authorises treatment
  execution.
- Missing patients, grants, revoked grants and expired grants return the same
  not-found result to a doctor.

## Verification

- Test creation, renewal, revoke, expiry, actor/tenant/role isolation and
  optimistic revision conflicts.
- Test every doctor-facing read path before exposing decrypted data.

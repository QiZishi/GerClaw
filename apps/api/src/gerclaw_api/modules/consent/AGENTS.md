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
- A doctor may receive only explicitly granted `health_profile_read` or
  `cga_report_read`; never writes, raw assessment answers, messages, Trace,
  documents, prescriptions, alerts, approvals or emergency access.
- Missing patients, grants, revoked grants and expired grants return the same
  not-found result to a doctor.

## Verification

- Test creation, renewal, revoke, expiry, actor/tenant/role isolation and
  optimistic revision conflicts.
- Test every doctor-facing read path before exposing decrypted data.

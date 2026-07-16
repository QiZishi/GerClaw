# Identity Module

## Responsibility

Own local account credentials and revocable refresh-session facts. It does not
grant clinical authority, verify a clinician licence, decide patient access,
or migrate visitor data.

## Invariants

- Store only an encrypted account display name and a keyed, non-reversible
  lookup fingerprint; never log a supplied username, password or token.
- Passwords use a versioned, memory-hard scrypt verifier. Refresh tokens are
  opaque, random, single-use-on-rotation values whose server record contains
  only a keyed fingerprint.
- A `doctor` account role is an interface identity only until credential
  verification and patient authorisation are implemented. It cannot grant a
  clinical scope, cross-patient read, approval decision or emergency override.
- Registration, login, refresh, logout and password change must be rate
  limited and return stable, enumeration-safe public errors.

## Verification

- Test malformed credentials, duplicate-name enumeration resistance, password
  verification, refresh rotation/replay, logout and password-change revocation.
- Test no plaintext password, username or refresh token occurs in stored
  columns, logs, Trace or metrics.

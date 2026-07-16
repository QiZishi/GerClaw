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
- Each of those operations writes an immutable PHI-free security audit fact.
  It may contain only an opaque actor ID, role, outcome and a keyed subject
  fingerprint; usernames, passwords, refresh tokens, IP addresses and clinical
  content are forbidden.

## Verification

- Test malformed credentials, duplicate-name enumeration resistance, password
  verification, refresh rotation/replay, logout and password-change revocation.
- Test no plaintext password, username or refresh token occurs in stored
  columns, logs, Trace or metrics.
- Test rejected credential/replay attempts as well as successful account
  operations produce only the bounded security-audit fields.

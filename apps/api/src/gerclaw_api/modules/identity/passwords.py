"""Versioned memory-hard password verification without external state."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGORITHM = "scrypt-v1"
_N = 16_384
_R = 8
_P = 1
_DKLEN = 64


def hash_password(password: str) -> str:
    """Create one self-describing scrypt verifier; plaintext never persists."""

    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return "$".join(
        (
            _ALGORITHM,
            str(_N),
            str(_R),
            str(_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    """Return false for malformed or mismatched verifiers without leaking why."""

    try:
        algorithm, n, r, p, salt_text, expected_text = encoded.split("$", maxsplit=5)
        if algorithm != _ALGORITHM:
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=_DKLEN,
        )
        return len(expected) == _DKLEN and hmac.compare_digest(actual, expected)
    except (ValueError, UnicodeError, MemoryError):
        return False

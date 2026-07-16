"""Memory-hard local-account verifier tests without any credential persistence."""

from gerclaw_api.modules.identity.passwords import hash_password, verify_password


def test_scrypt_verifier_accepts_only_the_original_password() -> None:
    encoded = hash_password("StrongPassword!2026")

    assert encoded.startswith("scrypt-v1$")
    assert "StrongPassword!2026" not in encoded
    assert verify_password("StrongPassword!2026", encoded) is True
    assert verify_password("wrong-password", encoded) is False


def test_scrypt_verifier_fails_closed_for_malformed_or_unsupported_data() -> None:
    assert verify_password("StrongPassword!2026", "not-a-verifier") is False
    assert verify_password("StrongPassword!2026", "argon2$v1$not-supported") is False

"""AES-256-GCM envelope encryption for sensitive PostgreSQL columns."""

from __future__ import annotations

import base64
import binascii
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import Text, TypeDecorator

_PREFIX = "enc:v1"
_cipher: FieldCipher | None = None


class EncryptionConfigurationError(RuntimeError):
    """Raised when encrypted persistence is used without a valid key."""


class FieldCipher:
    """Encrypt and authenticate values with a versioned key identifier."""

    def __init__(self, *, key_id: str, key_base64: str) -> None:
        try:
            key = base64.b64decode(key_base64, validate=True)
        except ValueError as error:
            raise EncryptionConfigurationError(
                "data encryption key must be valid base64"
            ) from error
        if len(key) != 32:
            raise EncryptionConfigurationError("data encryption key must decode to 32 bytes")
        self._key_id = key_id
        self._aes = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        """Return a nonce-bearing authenticated envelope."""

        nonce = os.urandom(12)
        ciphertext = self._aes.encrypt(nonce, plaintext.encode("utf-8"), self._key_id.encode())
        return ":".join(
            (
                _PREFIX,
                self._key_id,
                base64.urlsafe_b64encode(nonce).decode("ascii"),
                base64.urlsafe_b64encode(ciphertext).decode("ascii"),
            )
        )

    def decrypt(self, envelope: str) -> str:
        """Authenticate and decrypt one supported envelope."""

        parts = envelope.split(":", 4)
        if len(parts) != 5 or ":".join(parts[:2]) != _PREFIX:
            raise EncryptionConfigurationError("sensitive database value is not encrypted")
        _, _, key_id, nonce_base64, ciphertext_base64 = parts
        if key_id != self._key_id:
            raise EncryptionConfigurationError(f"unknown data encryption key id: {key_id}")
        try:
            nonce = base64.b64decode(nonce_base64, altchars=b"-_", validate=True)
            ciphertext = base64.b64decode(ciphertext_base64, altchars=b"-_", validate=True)
        except (binascii.Error, ValueError) as error:
            raise EncryptionConfigurationError("encrypted envelope is malformed") from error
        if len(nonce) != 12:
            raise EncryptionConfigurationError("encrypted envelope nonce is invalid")
        return self._aes.decrypt(nonce, ciphertext, key_id.encode()).decode("utf-8")


def configure_field_encryption(*, key_id: str, key_base64: str) -> None:
    """Configure the process-wide field cipher before database sessions are used."""

    global _cipher
    _cipher = FieldCipher(key_id=key_id, key_base64=key_base64)


def _configured_cipher() -> FieldCipher:
    if _cipher is None:
        raise EncryptionConfigurationError("field encryption has not been configured")
    return _cipher


class EncryptedText(TypeDecorator[str]):
    """SQLAlchemy text type that only stores AES-GCM envelopes."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        del dialect
        if value is None:
            return None
        return _configured_cipher().encrypt(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        del dialect
        if value is None:
            return None
        return _configured_cipher().decrypt(value)


class EncryptedJSON(TypeDecorator[Any]):
    """SQLAlchemy JSON value serialized into an authenticated encrypted text column."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        del dialect
        if value is None:
            return None
        plaintext = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return _configured_cipher().encrypt(plaintext)

    def process_result_value(self, value: str | None, dialect: Dialect) -> Any:
        del dialect
        if value is None:
            return None
        return json.loads(_configured_cipher().decrypt(value))

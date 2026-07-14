"""AES-256-GCM field encryption and SQLAlchemy type tests."""

from typing import cast

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy.engine.interfaces import Dialect

from gerclaw_api.encryption import (
    EncryptedJSON,
    EncryptedText,
    EncryptionConfigurationError,
    FieldCipher,
    configure_field_encryption,
)
from tests.conftest import TEST_DATA_KEY


def test_field_cipher_roundtrip_is_randomized_and_authenticated() -> None:
    cipher = FieldCipher(key_id="test-v1", key_base64=TEST_DATA_KEY)
    first = cipher.encrypt("患者张三")
    second = cipher.encrypt("患者张三")

    assert first.startswith("enc:v1:test-v1:")
    assert first != second
    assert "张三" not in first
    assert cipher.decrypt(first) == "患者张三"
    parts = first.split(":")
    parts[-1] = ("A" if parts[-1][0] != "A" else "B") + parts[-1][1:]
    with pytest.raises(InvalidTag):
        cipher.decrypt(":".join(parts))


@pytest.mark.parametrize("key", ["not-base64", "YQ=="])
def test_field_cipher_rejects_invalid_or_short_keys(key: str) -> None:
    with pytest.raises(EncryptionConfigurationError):
        FieldCipher(key_id="test-v1", key_base64=key)


def test_encrypted_sqlalchemy_types_never_bind_plaintext() -> None:
    configure_field_encryption(key_id="test-v1", key_base64=TEST_DATA_KEY)
    dialect = cast(Dialect, None)
    text_type = EncryptedText()
    json_type = EncryptedJSON()

    encrypted_text = text_type.process_bind_param("secret text", dialect)
    encrypted_json = json_type.process_bind_param({"name": "张三"}, dialect)
    assert encrypted_text is not None and "secret text" not in encrypted_text
    assert encrypted_json is not None and "张三" not in encrypted_json
    assert text_type.process_result_value(encrypted_text, dialect) == "secret text"
    assert json_type.process_result_value(encrypted_json, dialect) == {"name": "张三"}
    assert text_type.process_bind_param(None, dialect) is None
    assert json_type.process_result_value(None, dialect) is None

"""Tests for bounded redaction and strict audit telemetry."""

import time

import pytest

from gerclaw_api.security import (
    REDACTED,
    AuditPayloadError,
    redact_text,
    sanitize_payload,
    validate_audit_payload,
)


def test_redact_text_removes_common_phi_and_authorization() -> None:
    raw = (
        "电话13800138000 身份证11010519491231002X 邮箱patient@example.com "
        "Authorization: Bearer secret-token api_key=plain-secret "
        "postgresql://user:password@database/gerclaw sk-abcdefghijklmnop"
    )

    redacted = redact_text(raw)

    assert "13800138000" not in redacted
    assert "11010519491231002X" not in redacted
    assert "patient@example.com" not in redacted
    assert "secret-token" not in redacted
    assert "plain-secret" not in redacted
    assert "user:password" not in redacted
    assert "sk-abcdefghijklmnop" not in redacted
    assert "[PHONE]" in redacted
    assert "[ID_CARD]" in redacted
    assert "[EMAIL]" in redacted


def test_sanitize_payload_recurses_through_mappings_and_sequences() -> None:
    payload = {
        "token": "secret",
        "nested": [
            {"Cookie": "session=value", "patient_name": "张三"},
            "call 13900139000",
        ],
        "count": 3,
    }

    sanitized = sanitize_payload(payload)

    assert sanitized["token"] == REDACTED
    assert sanitized["nested"][0]["Cookie"] == REDACTED
    assert sanitized["nested"][0]["patient_name"] == REDACTED
    assert sanitized["nested"][1] == "call [PHONE]"
    assert sanitized["count"] == 3


def test_redaction_covers_header_variants_dynamic_keys_and_objects() -> None:
    class SecretObject:
        def __str__(self) -> str:
            return "Authorization: Bearer super-secret-token-value"

    raw = (
        "Cookie: session=super-secret-value password=super-secret-value "
        "Authorization=Basic dXNlcjpwYXNz"
    )
    redacted = redact_text(raw)
    sanitized = sanitize_payload(
        {"X-Token": "secret", "13800138000": SecretObject(), "patient@example.com": "value"}
    )

    assert "super-secret-value" not in redacted
    assert "dXNlcjpwYXNz" not in redacted
    assert "secret" not in str(sanitized)
    assert "13800138000" not in str(sanitized)
    assert "patient@example.com" not in str(sanitized)


def test_redaction_is_linear_for_long_delimiter_free_text() -> None:
    started = time.perf_counter()
    assert redact_text("x" * 200_000) == "x" * 200_000
    assert time.perf_counter() - started < 1.5


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "张三"},
        {"source": "北京市朝阳区幸福路1号"},
        {"score": float("nan")},
        {
            "token_usage": {
                "token_usage": {"token_usage": {"token_usage": {"token_usage": {"score": 1}}}}
            }
        },
    ],
)
def test_audit_payload_rejects_phi_nonfinite_and_deep_values(payload: object) -> None:
    with pytest.raises(AuditPayloadError):
        validate_audit_payload(payload)


def test_audit_payload_accepts_bounded_allowlisted_metadata() -> None:
    assert validate_audit_payload(
        {"model": "qwen-plus", "token_usage": {"input_tokens": 3, "output_tokens": 2}}
    ) == {"model": "qwen-plus", "token_usage": {"input_tokens": 3, "output_tokens": 2}}

"""Bounded PHI/secret redaction and audit-payload validation."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"
TRUNCATED = "[TRUNCATED]"
MAX_LOG_DEPTH = 8
MAX_LOG_ITEMS = 100
MAX_LOG_STRING_LENGTH = 4_096
MAX_AUDIT_DEPTH = 5
MAX_AUDIT_NODES = 200
MAX_AUDIT_STRING_LENGTH = 512

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "address",
        "api_key",
        "apikey",
        "authorization",
        "client_secret",
        "cookie",
        "email_address",
        "id_card",
        "id_number",
        "medical_record_number",
        "mobile",
        "password",
        "passwd",
        "patient_name",
        "phone_number",
        "private_key",
        "proxy_authorization",
        "pwd",
        "real_name",
        "refresh_token",
        "secret",
        "set_cookie",
        "token",
        "x_api_key",
        "x_token",
    },
)

# Trace payloads deliberately contain only bounded audit metadata. Free-form user or
# model text belongs in encrypted domain columns, never in searchable telemetry JSONB.
ALLOWED_AUDIT_KEYS = frozenset(
    {
        "cache_hit",
        "channel",
        "chunk_ids",
        "citation_count",
        "citation_ids",
        "document_count",
        "document_ids",
        "duration_ms",
        "error_code",
        "event_count",
        "feature",
        "input_tokens",
        "latency_ms",
        "model",
        "module",
        "operation",
        "output_tokens",
        "outcome",
        "provider",
        "protocol",
        "request_class",
        "result_code",
        "retry_count",
        "safety_flags",
        "score",
        "scores",
        "skill",
        "source",
        "success",
        "token_usage",
        "tool",
        "tool_name",
        "total_tokens",
        "version",
    }
)

# Every unbounded token is preceded by a literal or a negative boundary. The email
# and URI components are length-bounded so a long delimiter-free string remains O(n).
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])"
            r"(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)",
        ),
        "[ID_CARD]",
    ),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[PHONE]"),
    (
        re.compile(
            r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}"
            r"@[A-Za-z0-9.-]{1,189}\.[A-Za-z]{2,63}(?![A-Za-z])"
        ),
        "[EMAIL]",
    ),
    (
        re.compile(
            r"(?i)\b(authorization\s*[:=]\s*)"
            r"(?:(?:bearer|basic|digest)\s+)?[A-Za-z0-9._~+/\-=:,\"]+"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b((?:set-)?cookie\s*[:=]\s*)[^\s,\n]+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)\b((?:api[_-]?key|x-token|token|secret|client[_-]?secret|"
            r"private[_-]?key|password|passwd|pwd)\s*[:=]\s*)[^\s,;]+"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)(?<![a-z0-9+.-])([a-z][a-z0-9+.-]{0,31}://)"
            r"[^\s/:@]{1,256}:[^\s/@]{1,256}@"
        ),
        r"\1[REDACTED]@",
    ),
    (re.compile(r"(?<![A-Za-z0-9])(?:sk|ak)-[A-Za-z0-9_-]{12,}"), "[API_KEY]"),
)

_AUDIT_STRING_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+\-]{0,511}$")
_KEY_NORMALIZER = re.compile(r"[^a-z0-9]+")


class AuditPayloadError(ValueError):
    """Raised when telemetry attempts to contain non-audit or unbounded data."""


def _normalized_key(value: str) -> str:
    return _KEY_NORMALIZER.sub("_", value.casefold()).strip("_")


def redact_text(value: str) -> str:
    """Redact common Chinese PHI and credentials in bounded linear time."""

    redacted = value
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _safe_primitive(value: Any, *, depth: int, seen: set[int]) -> JsonValue:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return redact_text(value[:MAX_LOG_STRING_LENGTH])
    if depth >= MAX_LOG_DEPTH:
        return TRUNCATED

    object_id = id(value)
    if object_id in seen:
        return "[CYCLE]"
    if isinstance(value, Mapping):
        seen.add(object_id)
        result: dict[str, JsonValue] = {}
        for index, (raw_key, raw_value) in enumerate(value.items()):
            if index >= MAX_LOG_ITEMS:
                result[TRUNCATED] = TRUNCATED
                break
            key = redact_text(str(raw_key)[:MAX_AUDIT_STRING_LENGTH])
            result[key] = (
                REDACTED
                if _normalized_key(str(raw_key)) in SENSITIVE_KEYS
                else _safe_primitive(raw_value, depth=depth + 1, seen=seen)
            )
        seen.remove(object_id)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        seen.add(object_id)
        sequence_result: list[JsonValue] = [
            _safe_primitive(item, depth=depth + 1, seen=seen) for item in value[:MAX_LOG_ITEMS]
        ]
        if len(value) > MAX_LOG_ITEMS:
            sequence_result.append(TRUNCATED)
        seen.remove(object_id)
        return sequence_result
    return redact_text(str(value)[:MAX_LOG_STRING_LENGTH])


def sanitize_payload(value: Any) -> JsonValue:
    """Convert to bounded JSON primitives, then redact keys, values, and objects."""

    return _safe_primitive(value, depth=0, seen=set())


def validate_audit_payload(value: Any) -> dict[str, JsonValue]:
    """Validate a finite allowlisted JSON object suitable for telemetry JSONB."""

    if not isinstance(value, dict):
        raise AuditPayloadError("audit payload must be a JSON object")
    nodes = 0

    def validate(item: Any, *, depth: int) -> JsonValue:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_AUDIT_NODES:
            raise AuditPayloadError(f"audit payload exceeds {MAX_AUDIT_NODES} nodes")
        if depth > MAX_AUDIT_DEPTH:
            raise AuditPayloadError(f"audit payload exceeds depth {MAX_AUDIT_DEPTH}")
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise AuditPayloadError("audit payload floats must be finite")
            return item
        if isinstance(item, str):
            if len(item) > MAX_AUDIT_STRING_LENGTH or not _AUDIT_STRING_PATTERN.fullmatch(item):
                raise AuditPayloadError("audit strings must be bounded non-PHI identifiers")
            return item
        if isinstance(item, list):
            if len(item) > 50:
                raise AuditPayloadError("audit lists cannot exceed 50 items")
            return [validate(child, depth=depth + 1) for child in item]
        if isinstance(item, dict):
            result: dict[str, JsonValue] = {}
            for raw_key, child in item.items():
                if not isinstance(raw_key, str) or raw_key not in ALLOWED_AUDIT_KEYS:
                    raise AuditPayloadError(f"audit key is not allowlisted: {raw_key!r}")
                result[raw_key] = validate(child, depth=depth + 1)
            return result
        raise AuditPayloadError(f"audit payload contains non-JSON type: {type(item).__name__}")

    result = validate(value, depth=0)
    if not isinstance(result, dict):  # pragma: no cover - guarded above
        raise AuditPayloadError("audit payload changed type")
    return result

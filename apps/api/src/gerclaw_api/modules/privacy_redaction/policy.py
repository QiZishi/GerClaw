"""Purpose-bound redaction before a public online-search provider call."""

from __future__ import annotations

import re

from gerclaw_api.modules.privacy_redaction.models import (
    RedactionCategory,
    RedactionFinding,
    RedactionResult,
)
from gerclaw_api.security import redact_text

PRIVACY_REDACTION_POLICY_VERSION = "1.0.0"

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PERSON_NAME_PATTERNS = (
    re.compile(
        r"(?:我叫|姓名(?:是|为|[:\uFF1A])?|患者(?:姓名)?(?:是|为|[:\uFF1A])?)\s*[\u4e00-\u9fff]{2,4}"
    ),
    re.compile(r"(?:name\s*[:=]\s*)[A-Za-z][A-Za-z .'-]{1,80}", re.IGNORECASE),
)
_CATEGORY_PATTERNS: tuple[tuple[RedactionCategory, re.Pattern[str]], ...] = (
    (RedactionCategory.PHONE, re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    (
        RedactionCategory.ID_CARD,
        re.compile(
            r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])"
            r"(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"
        ),
    ),
    (
        RedactionCategory.EMAIL,
        re.compile(
            r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}"
            r"@[A-Za-z0-9.-]{1,189}\.[A-Za-z]{2,63}(?![A-Za-z])"
        ),
    ),
    (
        RedactionCategory.CREDENTIAL,
        re.compile(
            r"(?i)\b(?:api[_-]?key|x-token|token|secret|client[_-]?secret|"
            r"private[_-]?key|password|passwd|pwd)\s*[:=]"
        ),
    ),
)


class PrivacyRedactionError(ValueError):
    """Raised when an external-search egress projection would be empty or oversized."""


def _findings(value: str) -> tuple[RedactionFinding, ...]:
    counts: dict[RedactionCategory, int] = {}
    control_count = len(_CONTROL.findall(value))
    if control_count:
        counts[RedactionCategory.CONTROL] = control_count
    name_count = sum(len(pattern.findall(value)) for pattern in _PERSON_NAME_PATTERNS)
    if name_count:
        counts[RedactionCategory.PERSON_NAME] = name_count
    for category, pattern in _CATEGORY_PATTERNS:
        count = len(pattern.findall(value))
        if count:
            counts[category] = count
    return tuple(
        RedactionFinding(category=category, count=count)
        for category, count in sorted(counts.items(), key=lambda item: item[0].value)
    )


def redact_external_search_query(query: str) -> RedactionResult:
    """Return a bounded query safe to send to an external evidence provider.

    The decision summary deliberately includes category counts only: callers must
    not persist input text, matched spans or replacement positions in Trace,
    metrics or a provider-audit record.
    """

    if len(query) > 4_000:
        raise PrivacyRedactionError("search query exceeds the privacy policy size limit")
    findings = _findings(query)
    sanitized = redact_text(_CONTROL.sub(" ", query))
    for pattern in _PERSON_NAME_PATTERNS:
        sanitized = pattern.sub("患者", sanitized)
    normalized = " ".join(sanitized.split()).strip()
    if not normalized:
        raise PrivacyRedactionError("search query cannot be blank after privacy filtering")
    return RedactionResult(
        text=normalized,
        policy_version=PRIVACY_REDACTION_POLICY_VERSION,
        findings=findings,
    )

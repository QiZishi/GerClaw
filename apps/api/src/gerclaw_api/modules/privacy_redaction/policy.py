"""Purpose-bound redaction before a public online-search provider call."""

from __future__ import annotations

import re

from gerclaw_api.modules.privacy_redaction.models import (
    EgressPurpose,
    RedactionCategory,
    RedactionFinding,
    RedactionResult,
)
from gerclaw_api.security import redact_text

PRIVACY_REDACTION_POLICY_VERSION = "1.1.0"
MODEL_PROMPT_REDACTION_POLICY_VERSION = "1.0.0"

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
    """Raised when an external egress projection would be empty or oversized."""


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


def _redact_external_text(
    text: str,
    *,
    purpose: EgressPurpose,
    person_replacement: str,
    max_characters: int = 4_000,
    collapse_whitespace: bool = True,
    policy_version: str = PRIVACY_REDACTION_POLICY_VERSION,
) -> RedactionResult:
    """Return a bounded purpose-specific projection safe for an external provider.

    The decision summary deliberately includes category counts only: callers must
    not persist input text, matched spans or replacement positions in Trace,
    metrics or a provider-audit record.
    """

    if len(text) > max_characters:
        raise PrivacyRedactionError("egress text exceeds the privacy policy size limit")
    findings = _findings(text)
    sanitized = redact_text(_CONTROL.sub(" ", text))
    for pattern in _PERSON_NAME_PATTERNS:
        sanitized = pattern.sub(person_replacement, sanitized)
    normalized = " ".join(sanitized.split()).strip() if collapse_whitespace else sanitized.strip()
    if not normalized:
        raise PrivacyRedactionError("egress text cannot be blank after privacy filtering")
    return RedactionResult(
        text=normalized,
        purpose=purpose,
        policy_version=policy_version,
        findings=findings,
    )


def redact_external_search_query(query: str) -> RedactionResult:
    """Return a clinical-intent query safe for an external evidence provider."""

    return _redact_external_text(
        query,
        purpose=EgressPurpose.EXTERNAL_SEARCH_QUERY,
        person_replacement="患者",
    )


def redact_external_tts_text(text: str) -> RedactionResult:
    """Remove identifiers before an external TTS provider receives spoken text."""

    return _redact_external_text(
        text,
        purpose=EgressPurpose.EXTERNAL_TTS,
        person_replacement="您",
    )


def redact_external_model_prompt(text: str) -> RedactionResult:
    """Project one model-prompt string without collapsing its Markdown structure."""

    return _redact_external_text(
        text,
        purpose=EgressPurpose.EXTERNAL_MODEL_PROMPT,
        person_replacement="患者",
        max_characters=100_000,
        collapse_whitespace=False,
        policy_version=MODEL_PROMPT_REDACTION_POLICY_VERSION,
    )

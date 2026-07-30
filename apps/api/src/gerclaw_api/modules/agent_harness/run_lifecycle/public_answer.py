"""Deterministic reader-facing projection for a validated answer attempt."""

from __future__ import annotations

import json
import re

_TERMINAL_TEMPLATE_SECTION = re.compile(
    r"""
    (?:\n[ \t]*)*
    (?:---[ \t]*(?:\n[ \t]*)*)?
    (?:⚠️?[ \t]*)?
    \*{0,2}(?:风险提示|安全提示|免责声明|温馨提示)\*{0,2}[\uff1a: \t]*
    (?P<body>.+?)
    [ \t\n]*\Z
    """,
    re.DOTALL | re.VERBOSE,
)
_GENERIC_TEMPLATE_SIGNALS: tuple[re.Pattern[str], ...] = (
    re.compile(r"以上(?:建议|内容).{0,32}(?:通用|一般|仅供)", re.DOTALL),
    re.compile(
        r"(?:每个人|每位患者|每个患者|每位老人|每个老人).{0,48}(?:差异|不同)",
        re.DOTALL,
    ),
    re.compile(r"(?:本回答|本内容).{0,32}(?:仅供参考|不能替代)", re.DOTALL),
)
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_INLINE_ORDERED_LIST_BOUNDARY = re.compile(
    r"(?<=[。！？!?])\s*(?=(?:[2-9]|[1-9]\d)\.\s)"  # noqa: RUF001
)
_CLINICAL_STATE_ENVELOPE = re.compile(
    r"<\s*final-clinical-state\s*>(?P<payload>.*?)"
    r"<\s*/\s*final-clinical-state\s*>",
    re.DOTALL | re.IGNORECASE,
)


def _project_recommendations(payload: str) -> str | None:
    """Project a known private clinical-state envelope into reader-facing prose."""

    try:
        document: object = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    raw_recommendations = document.get("recommendations")
    if not isinstance(raw_recommendations, list):
        return None
    recommendations: list[str] = []
    for item in raw_recommendations:
        detail: object = item.get("detail") if isinstance(item, dict) else item
        if isinstance(detail, str) and (normalized := detail.strip()):
            recommendations.append(normalized)
    if not recommendations:
        return None
    return "\n".join(
        f"{index}. {recommendation}"
        for index, recommendation in enumerate(recommendations, start=1)
    )


def _replace_private_clinical_state(match: re.Match[str]) -> str:
    projected = _project_recommendations(match.group("payload"))
    return projected if projected is not None else match.group(0)


def project_public_answer(text: str) -> str:
    """Remove only clearly generic terminal boilerplate from a valid answer.

    Clinical content, citations and situation-specific risk instructions remain
    untouched. The Harness adds its single canonical disclaimer afterwards.
    """

    candidate = _CLINICAL_STATE_ENVELOPE.sub(_replace_private_clinical_state, text).strip()
    match = _TERMINAL_TEMPLATE_SECTION.search(candidate)
    if match is not None and any(
        pattern.search(match.group("body")) is not None for pattern in _GENERIC_TEMPLATE_SIGNALS
    ):
        candidate = candidate[: match.start()].rstrip()
    candidate = _INLINE_ORDERED_LIST_BOUNDARY.sub("\n", candidate)
    return _EXCESS_BLANK_LINES.sub("\n\n", candidate)

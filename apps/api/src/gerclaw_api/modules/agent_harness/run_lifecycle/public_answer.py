"""Deterministic reader-facing projection for a validated answer attempt."""

from __future__ import annotations

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


def project_public_answer(text: str) -> str:
    """Remove only clearly generic terminal boilerplate from a valid answer.

    Clinical content, citations and situation-specific risk instructions remain
    untouched. The Harness adds its single canonical disclaimer afterwards.
    """

    candidate = text.strip()
    match = _TERMINAL_TEMPLATE_SECTION.search(candidate)
    if match is not None and any(
        pattern.search(match.group("body")) is not None for pattern in _GENERIC_TEMPLATE_SIGNALS
    ):
        candidate = candidate[: match.start()].rstrip()
    return _EXCESS_BLANK_LINES.sub("\n\n", candidate)

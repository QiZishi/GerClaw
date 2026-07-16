# ruff: noqa: RUF001
"""Committed, reviewed synthetic canaries for privacy egress policy 1.1.0."""

from __future__ import annotations

from gerclaw_api.modules.evals.models import PrivacyRedactionEvalCase
from gerclaw_api.modules.privacy_redaction.models import (
    EgressPurpose,
    RedactionCategory,
    RedactionFinding,
)


def _finding(category: RedactionCategory, count: int = 1) -> RedactionFinding:
    return RedactionFinding(category=category, count=count)


PRIVACY_REDACTION_GOLDEN_CASES: tuple[PrivacyRedactionEvalCase, ...] = (
    PrivacyRedactionEvalCase(
        case_id="privacy-redaction.search.labeled-identifiers",
        title="search egress removes labeled identifiers and credentials",
        synthetic_input=(
            "患者姓名：赵安，电话 13912345678，邮箱 test@example.com，"
            "身份证 11010519491231002X，token=synthetic-secret 老年跌倒预防"
        ),
        purpose=EgressPurpose.EXTERNAL_SEARCH_QUERY,
        expected_redacted_text=(
            "患者，电话 [PHONE]，邮箱 [EMAIL]，身份证 [ID_CARD]，token=[REDACTED] 老年跌倒预防"
        ),
        expected_findings=(
            _finding(RedactionCategory.CREDENTIAL),
            _finding(RedactionCategory.EMAIL),
            _finding(RedactionCategory.ID_CARD),
            _finding(RedactionCategory.PERSON_NAME),
            _finding(RedactionCategory.PHONE),
        ),
    ),
    PrivacyRedactionEvalCase(
        case_id="privacy-redaction.search.control-and-english-name",
        title="search egress normalizes controls and English name labels",
        synthetic_input="\x00 name: Alex Example\t老年营养评估",
        purpose=EgressPurpose.EXTERNAL_SEARCH_QUERY,
        expected_redacted_text="患者 老年营养评估",
        expected_findings=(
            _finding(RedactionCategory.CONTROL),
            _finding(RedactionCategory.PERSON_NAME),
        ),
    ),
    PrivacyRedactionEvalCase(
        case_id="privacy-redaction.tts.labeled-identifiers",
        title="TTS egress removes spoken identifiers before provider use",
        synthetic_input=(
            "患者姓名：陈宁，电话 13800138000，password=synthetic-secret 请慢一点朗读。"
        ),
        purpose=EgressPurpose.EXTERNAL_TTS,
        expected_redacted_text="您，电话 [PHONE]，password=[REDACTED] 请慢一点朗读。",
        expected_findings=(
            _finding(RedactionCategory.CREDENTIAL),
            _finding(RedactionCategory.PERSON_NAME),
            _finding(RedactionCategory.PHONE),
        ),
    ),
    PrivacyRedactionEvalCase(
        case_id="privacy-redaction.tts.safe-text",
        title="TTS egress preserves ordinary spoken instruction",
        synthetic_input="请慢一点朗读今天的用药提醒。",
        purpose=EgressPurpose.EXTERNAL_TTS,
        expected_redacted_text="请慢一点朗读今天的用药提醒。",
    ),
)

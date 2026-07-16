# ruff: noqa: RUF001
"""Regression canaries for versioned external-search privacy egress."""

from __future__ import annotations

import pytest

from gerclaw_api.modules.privacy_redaction.models import RedactionCategory
from gerclaw_api.modules.privacy_redaction.policy import (
    PRIVACY_REDACTION_POLICY_VERSION,
    PrivacyRedactionError,
    redact_external_search_query,
)


def test_external_search_policy_redacts_identifiers_without_a_reversible_audit() -> None:
    raw = (
        "患者姓名：李雷，电话 13800138000，邮箱 old@example.com，"
        "身份证 11010519491231002X，token=secret-value 高血压指南"
    )

    result = redact_external_search_query(raw)

    assert result.text == (
        "患者，电话 [PHONE]，邮箱 [EMAIL]，身份证 [ID_CARD]，"
        "token=[REDACTED] 高血压指南"
    )
    assert result.policy_version == PRIVACY_REDACTION_POLICY_VERSION
    findings = {item.category: item.count for item in result.findings}
    assert findings == {
        RedactionCategory.PERSON_NAME: 1,
        RedactionCategory.PHONE: 1,
        RedactionCategory.EMAIL: 1,
        RedactionCategory.ID_CARD: 1,
        RedactionCategory.CREDENTIAL: 1,
    }
    rendered_findings = result.model_dump_json()
    for value in ("李雷", "13800138000", "old@example.com", "11010519491231002X", "secret-value"):
        assert value not in rendered_findings


def test_external_search_policy_counts_control_characters_and_rejects_blank_input() -> None:
    result = redact_external_search_query("\x00 老年跌倒风险 \t")

    assert result.text == "老年跌倒风险"
    assert len(result.findings) == 1
    assert result.findings[0].category is RedactionCategory.CONTROL
    assert result.findings[0].count == 1
    with pytest.raises(PrivacyRedactionError, match="blank"):
        redact_external_search_query("\x00\t")


def test_external_search_policy_rejects_oversized_input() -> None:
    with pytest.raises(PrivacyRedactionError, match="size limit"):
        redact_external_search_query("x" * 4_001)

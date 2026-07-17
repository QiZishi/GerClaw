"""Versioned five-prescription intake definition for a clinician-review draft."""
# ruff: noqa: RUF001

from __future__ import annotations

from gerclaw_api.modules.input_output.clinical_intake import (
    CLINICAL_INTAKE_VERSION,
    ClinicalIntakeDefinition,
    ClinicalIntakeField,
)

PRESCRIPTION_INTAKE_DEFINITION = ClinicalIntakeDefinition(
    kind="prescription",
    version=CLINICAL_INTAKE_VERSION,
    title="五大处方信息收集",
    description="填写后可生成带本地医学证据的待临床复核草案；它不是正式处方或诊断。",
    fields=(
        ClinicalIntakeField(
            id="health_goal",
            label="您最希望改善的健康问题",
            required=True,
            max_length=500,
            placeholder="例如：想和医生讨论活动耐受、睡眠或日常照护困扰",
        ),
        ClinicalIntakeField(
            id="current_concerns",
            label="目前需要医生了解的情况",
            required=True,
            max_length=1_000,
            placeholder="可简要描述症状、限制或生活中的困难",
        ),
        ClinicalIntakeField(
            id="current_medications",
            label="正在使用的药物",
            required=False,
            max_length=1_000,
            placeholder="请按药盒名称填写；不会在此页面给出调药建议",
        ),
    ),
)

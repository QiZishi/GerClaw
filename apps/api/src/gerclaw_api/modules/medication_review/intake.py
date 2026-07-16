"""Versioned, non-clinical medication-review intake definition."""
# ruff: noqa: RUF001

from __future__ import annotations

from gerclaw_api.modules.input_output.clinical_intake import (
    CLINICAL_INTAKE_VERSION,
    ClinicalIntakeDefinition,
    ClinicalIntakeField,
)

MEDICATION_REVIEW_INTAKE_DEFINITION = ClinicalIntakeDefinition(
    kind="medication_review",
    version=CLINICAL_INTAKE_VERSION,
    title="用药审查信息收集",
    description="仅收集需要医生核对的信息；当前不会给出停药、加药或剂量调整结论。",
    fields=(
        ClinicalIntakeField(
            id="medication_list",
            label="正在使用的药物",
            required=True,
            max_length=1_500,
            placeholder="请按药盒逐项填写药物名称；剂量不确定时可留待医生核对",
        ),
        ClinicalIntakeField(
            id="review_goal",
            label="希望医生重点核对的问题",
            required=True,
            max_length=500,
            placeholder="例如：担心重复用药、服药困难或不适反应",
        ),
        ClinicalIntakeField(
            id="adverse_reactions",
            label="曾出现的不适或过敏反应",
            required=False,
            max_length=1_000,
            placeholder="请描述已经发生的反应；紧急不适请立即就医",
        ),
    ),
)

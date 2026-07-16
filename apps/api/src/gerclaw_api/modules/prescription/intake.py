"""Versioned, non-clinical intake definitions for future governed workflows."""
# ruff: noqa: RUF001

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ClinicalIntakeKind = Literal["prescription", "medication_review"]
CLINICAL_INTAKE_VERSION = "clinical-intake-v1"


@dataclass(frozen=True)
class ClinicalIntakeField:
    """A server-owned field definition; values are encrypted at rest."""

    id: str
    label: str
    required: bool
    max_length: int
    placeholder: str


@dataclass(frozen=True)
class ClinicalIntakeDefinition:
    """A non-clinical collection contract that never contains advice or dosing rules."""

    kind: ClinicalIntakeKind
    version: str
    title: str
    description: str
    fields: tuple[ClinicalIntakeField, ...]


CLINICAL_INTAKE_DEFINITIONS: dict[ClinicalIntakeKind, ClinicalIntakeDefinition] = {
    "prescription": ClinicalIntakeDefinition(
        kind="prescription",
        version=CLINICAL_INTAKE_VERSION,
        title="五大处方信息收集",
        description="仅收集您希望与医生讨论的情况；当前不会生成处方或生活方式建议。",
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
    ),
    "medication_review": ClinicalIntakeDefinition(
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
    ),
}


def intake_definition(kind: ClinicalIntakeKind) -> ClinicalIntakeDefinition:
    """Return one immutable, server-owned definition."""

    return CLINICAL_INTAKE_DEFINITIONS[kind]

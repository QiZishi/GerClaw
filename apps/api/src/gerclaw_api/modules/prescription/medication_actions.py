"""Normalize medication-action language before STEP enforcement."""
# ruff: noqa: RUF001

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MedicationActionKind(StrEnum):
    START = "start"
    STOP = "stop"
    REPLACE = "replace"
    DOSE_CHANGE = "dose_change"


class MedicationAction(BaseModel):
    """One bounded, code-detected medication action candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: MedicationActionKind
    matched_text: str = Field(min_length=1, max_length=80)


_ACTION_PATTERNS: tuple[tuple[MedicationActionKind, re.Pattern[str]], ...] = (
    (
        MedicationActionKind.START,
        re.compile(r"(?:开始|启用|加用|新增)(?:服用|使用|用药)?"),
    ),
    (
        MedicationActionKind.STOP,
        re.compile(
            r"(?:(?:不要|不再|别再|停止|暂停|中止)(?:继续)?(?:服用|使用|吃)"
            r"|停用|停药|停服|停止用药|撤掉|撤除)"
        ),
    ),
    (
        MedicationActionKind.REPLACE,
        re.compile(r"(?:替换为?|替(?:换)?成|替为|换(?:成|为|用)?|改成|改为|改用|更换为?)"),
    ),
    (
        MedicationActionKind.DOSE_CHANGE,
        re.compile(
            r"(?:(?:调整|调节|增加|减少|上调|下调|提高|降低|加大|减小)"
            r".{0,3}(?:剂量|用量)"
            r"|(?:剂量|用量)(?:调整|增加|减少|上调|下调|改为|改至|改成)"
            r"|加量|减量|增量"
            r"|(?:改至|改到)\s*\d+(?:\.\d+)?)"
        ),
    ),
)
_REGIMEN_PATTERN = re.compile(
    r"[A-Za-z\u4e00-\u9fff]{2,40}\s*"
    r"\d+(?:\.\d+)?\s*(?:mg|g|mcg|ug|ml|毫克|克|片|粒)"
    r".{0,16}(?:每日|每天|每晚|每晨|一日|每\d+小时)"
    r".{0,8}(?:\d+次|一次|两次|三次)",
    re.IGNORECASE,
)
_NEGATED_PREFIX = re.compile(
    r"(?:不|勿|禁止|避免|不得|不可|无需|未)"
    r"(?:自行|擅自|立即|直接|随意|轻易|应|要|可|建议|考虑)?"
    r"[^，,。；;\n]{0,6}$"
)
_CONDITIONAL_PREFIX = re.compile(r"(?:涉及|如需|若需|是否|由医生决定是否)[^，,。；;\n]{0,10}$")


class MedicationActionClassifier:
    """Detect medication actions while preserving negated safety guardrails."""

    def classify(
        self,
        text: str,
        *,
        include_regimen: bool,
    ) -> tuple[MedicationAction, ...]:
        actions: list[MedicationAction] = []
        for clause in re.split(r"[。；;\n]", text):
            actions.extend(self._classify_clause(clause))
            if include_regimen:
                for match in _REGIMEN_PATTERN.finditer(clause):
                    if not self._is_guardrail(clause, match.start(), match.end()):
                        actions.append(
                            MedicationAction(
                                kind=MedicationActionKind.DOSE_CHANGE,
                                matched_text=match.group(0),
                            )
                        )
        return tuple(actions)

    @staticmethod
    def _classify_clause(clause: str) -> list[MedicationAction]:
        actions: list[MedicationAction] = []
        for kind, pattern in _ACTION_PATTERNS:
            for match in pattern.finditer(clause):
                if MedicationActionClassifier._is_guardrail(clause, match.start(), match.end()):
                    continue
                actions.append(
                    MedicationAction(
                        kind=kind,
                        matched_text=match.group(0),
                    )
                )
        return actions

    @staticmethod
    def _is_guardrail(clause: str, start: int, end: int) -> bool:
        prefix = clause[max(0, start - 20) : start]
        suffix = clause[end : end + 20]
        if _NEGATED_PREFIX.search(prefix):
            return True
        return bool(_CONDITIONAL_PREFIX.search(prefix) and "时" in suffix)


def is_reported_medication_record(field: str, reported_medications: str) -> bool:
    """Accept only a regimen copied from the caller's current-medication record."""

    if not reported_medications.strip():
        return False

    def normalize(value: str) -> str:
        return re.sub(r"[\s，,。；;：:]", "", value).removeprefix("已记录用药信息")

    field_value = normalize(field)
    reported_value = normalize(reported_medications)
    return bool(
        field_value
        and reported_value
        and (field_value in reported_value or reported_value in field_value)
    )

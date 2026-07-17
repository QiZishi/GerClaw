"""Deterministic medication-rule evaluation with explicit source coverage.

The engine intentionally evaluates only the shipped, versioned rules.  A rule
miss is never presented as proof that a regimen is safe, and no model, web
search, or external medication database receives the medication list.
"""
# ruff: noqa: RUF001

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.modules.medication_review.models import (
    MedicationListEntry,
    MedicationReviewDraft,
    MedicationReviewFinding,
    MedicationRiskLevel,
    MedicationRuleCoverage,
    MedicationRuleSource,
    ReviewedMedication,
)
from gerclaw_api.modules.medication_review.reconciliation import (
    MedicationReconciliationInputError,
    reconcile_medication_list,
)

_RULESET_PATH = Path(__file__).with_name("rules") / "core-v1.json"
_SEVERITY_RANK = {"contraindicated": 0, "major": 1, "moderate": 2, "minor": 3}
_ONCE_DAILY = re.compile(
    r"(?:每日|每天|一日)\s*一?次|(?:^|[^0-9])1\s*次\s*/\s*(?:日|d)(?:$|[^a-z])|\bqd\b|once\s+daily",
    re.IGNORECASE,
)
_MILLIGRAM = re.compile(r"(?<![0-9.])(\d+(?:\.\d+)?)\s*(?:mg|毫克)", re.IGNORECASE)


class MedicationRulesInputError(ValueError):
    """A review cannot run without a bounded medication list."""


class _DdiRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,95}$")
    drugs: tuple[str, str]
    severity: MedicationRiskLevel
    conclusion: str = Field(min_length=1, max_length=1_000)
    clinician_action: str = Field(min_length=1, max_length=1_000)
    elderly_note: str | None = Field(default=None, max_length=1_000)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=4)


class _DoseRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,95}$")
    drug: str = Field(min_length=1, max_length=100)
    max_daily_mg: float = Field(gt=0, le=100_000)
    severity: MedicationRiskLevel
    conclusion: str = Field(min_length=1, max_length=1_000)
    clinician_action: str = Field(min_length=1, max_length=1_000)
    elderly_note: str | None = Field(default=None, max_length=1_000)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=4)


class _BeersRule(BaseModel):
    """A narrowly sourced older-adult PIM signal, never a full Beers table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,95}$")
    drugs: tuple[str, ...] = Field(min_length=1, max_length=30)
    minimum_age: int = Field(ge=65, le=130)
    severity: MedicationRiskLevel
    conclusion: str = Field(min_length=1, max_length=1_000)
    clinician_action: str = Field(min_length=1, max_length=1_000)
    elderly_note: str | None = Field(default=None, max_length=1_000)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=4)


class _RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(pattern=r"^medication-rules-v[0-9]+$")
    sources: tuple[MedicationRuleSource, ...] = Field(min_length=1, max_length=20)
    aliases: dict[str, tuple[str, ...]] = Field(min_length=1, max_length=500)
    ddi_rules: tuple[_DdiRule, ...] = Field(max_length=2_000)
    dose_rules: tuple[_DoseRule, ...] = Field(max_length=2_000)
    beers_rules: tuple[_BeersRule, ...] = Field(max_length=2_000)

    @model_validator(mode="after")
    def validate_references(self) -> _RuleSet:
        """Reject an artifact with a dangling source or unmatchable drug name."""

        source_ids = {source.source_id for source in self.sources}
        references = (
            *((rule.id, rule.source_ids, rule.drugs) for rule in self.ddi_rules),
            *((rule.id, rule.source_ids, (rule.drug,)) for rule in self.dose_rules),
            *((rule.id, rule.source_ids, rule.drugs) for rule in self.beers_rules),
        )
        for rule_id, rule_source_ids, drugs in references:
            if missing_sources := set(rule_source_ids) - source_ids:
                raise ValueError(f"rule {rule_id} references unknown sources: {missing_sources}")
            if missing_aliases := set(drugs) - set(self.aliases):
                raise ValueError(f"rule {rule_id} references unknown aliases: {missing_aliases}")
        return self


@lru_cache(maxsize=1)
def _ruleset() -> _RuleSet:
    """Load a package-owned rule artifact once and validate it before use."""

    try:
        raw = json.loads(_RULESET_PATH.read_text(encoding="utf-8"))
        return _RuleSet.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise MedicationRulesInputError("installed medication rules are unavailable") from error


def review_medication_list(
    *, intake_id: uuid.UUID, medication_list: str, patient_age: int | None = None
) -> MedicationReviewDraft:
    """Return a reviewable artifact from exact aliases and installed rules only."""

    try:
        reconciliation = reconcile_medication_list(
            intake_id=intake_id, medication_list=medication_list
        )
    except MedicationReconciliationInputError as error:
        raise MedicationRulesInputError("medication list exceeds the review limit") from error
    if not reconciliation.entries:
        raise MedicationRulesInputError("medication list is required")

    ruleset = _ruleset()
    recognized_by_position = {
        entry.position: _recognized_generic_names(entry.text, ruleset.aliases)
        for entry in reconciliation.entries
    }
    reviewed = tuple(
        ReviewedMedication(
            position=entry.position,
            text=entry.text,
            recognized_generic_names=recognized_by_position[entry.position],
        )
        for entry in reconciliation.entries
    )
    findings = [
        *_ddi_findings(ruleset, recognized_by_position, patient_age),
        *_dose_findings(ruleset, reconciliation.entries, recognized_by_position, patient_age),
        *_beers_findings(ruleset, recognized_by_position, patient_age),
        *_duplicate_findings(recognized_by_position),
        *_polypharmacy_findings(len(reconciliation.entries)),
    ]
    findings.sort(key=lambda finding: (_SEVERITY_RANK[finding.severity], finding.finding_id))
    recognized_entries = sum(bool(names) for names in recognized_by_position.values())
    return MedicationReviewDraft(
        intake_id=intake_id,
        ruleset_version=ruleset.version,
        patient_age=patient_age,
        reviewed_medications=reviewed,
        findings=tuple(findings),
        sources=ruleset.sources,
        coverage=MedicationRuleCoverage(
            ddi="limited_source_traceable",
            dose="limited_source_traceable",
            beers="limited_source_traceable",
        ),
        unrecognized_entry_count=len(reviewed) - recognized_entries,
        conclusion=_conclusion(findings),
    )


def _normalized(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def _recognized_generic_names(
    text: str, aliases: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    normalized = _normalized(text)
    return tuple(
        generic
        for generic, names in aliases.items()
        if any(_normalized(alias) in normalized for alias in names)
    )


def _ddi_findings(
    ruleset: _RuleSet,
    recognized_by_position: dict[int, tuple[str, ...]],
    patient_age: int | None,
) -> list[MedicationReviewFinding]:
    present = {generic for names in recognized_by_position.values() for generic in names}
    findings: list[MedicationReviewFinding] = []
    for rule in ruleset.ddi_rules:
        if not set(rule.drugs).issubset(present):
            continue
        severity, age_escalated = _age_adjust(rule.severity, patient_age)
        findings.append(
            MedicationReviewFinding(
                finding_id=rule.id,
                kind="ddi",
                severity=severity,
                title=f"{rule.drugs[0]} + {rule.drugs[1]}：{_severity_label(severity)}风险",
                involved_generic_names=rule.drugs,
                conclusion=rule.conclusion,
                clinician_action=_review_action(rule.clinician_action),
                elderly_note=rule.elderly_note,
                source_ids=rule.source_ids,
                age_escalated=age_escalated,
            )
        )
    return findings


def _dose_findings(
    ruleset: _RuleSet,
    entries: tuple[MedicationListEntry, ...],
    recognized_by_position: dict[int, tuple[str, ...]],
    patient_age: int | None,
) -> list[MedicationReviewFinding]:
    findings: list[MedicationReviewFinding] = []
    for entry in entries:
        daily_mg = _once_daily_milligrams(entry.text)
        if daily_mg is None:
            continue
        for rule in ruleset.dose_rules:
            if (
                rule.drug not in recognized_by_position[entry.position]
                or daily_mg <= rule.max_daily_mg
            ):
                continue
            severity, age_escalated = _age_adjust(rule.severity, patient_age)
            findings.append(
                MedicationReviewFinding(
                    finding_id=f"{rule.id}_{entry.position}",
                    kind="dose",
                    severity=severity,
                    title=f"{rule.drug}：录入日剂量 {daily_mg:g} mg 超出规则阈值",
                    involved_generic_names=(rule.drug,),
                    conclusion=rule.conclusion,
                    clinician_action=_review_action(rule.clinician_action),
                    elderly_note=rule.elderly_note,
                    source_ids=rule.source_ids,
                    age_escalated=age_escalated,
                )
            )
    return findings


def _duplicate_findings(
    recognized_by_position: dict[int, tuple[str, ...]],
) -> list[MedicationReviewFinding]:
    positions_by_generic: dict[str, list[int]] = {}
    for position, names in recognized_by_position.items():
        for generic in names:
            positions_by_generic.setdefault(generic, []).append(position)
    return [
        MedicationReviewFinding(
            finding_id=f"duplicate_generic_{index}",
            kind="duplicate",
            severity="moderate",
            title=f"{generic}：在多条录入中被识别",
            involved_generic_names=(generic,),
            conclusion=(
                f"{generic}在第{'、'.join(map(str, positions))}条中均被识别，"
                "需要核对是否为重复记录或重复用药。"
            ),
            clinician_action="请由医师或药师核对每条药物的实际名称、剂型、用法和开方来源。",
            elderly_note="老年人多重用药时，应进行完整的药物核对。",
        )
        for index, (generic, positions) in enumerate(positions_by_generic.items(), start=1)
        if len(positions) > 1
    ]


def _beers_findings(
    ruleset: _RuleSet,
    recognized_by_position: dict[int, tuple[str, ...]],
    patient_age: int | None,
) -> list[MedicationReviewFinding]:
    """Return only age-qualified, locally sourced PIM review signals.

    The installed source is limited to a specific older-adult insomnia statement.
    A medication list does not establish indication, so every hit requires that
    the clinician verify whether the condition in the source actually applies.
    """

    if patient_age is None:
        return []
    present = {generic for names in recognized_by_position.values() for generic in names}
    findings: list[MedicationReviewFinding] = []
    for rule in ruleset.beers_rules:
        matched = tuple(drug for drug in rule.drugs if drug in present)
        if patient_age < rule.minimum_age or not matched:
            continue
        findings.append(
            MedicationReviewFinding(
                finding_id=rule.id,
                kind="beers",
                severity=rule.severity,
                title=f"≥{rule.minimum_age} 岁：{ '、'.join(matched) } 老年用药核对提示",
                involved_generic_names=matched,
                conclusion=rule.conclusion,
                clinician_action=_review_action(rule.clinician_action),
                elderly_note=rule.elderly_note,
                source_ids=rule.source_ids,
            )
        )
    return findings


def _polypharmacy_findings(entry_count: int) -> list[MedicationReviewFinding]:
    if entry_count < 5:
        return []
    severity: MedicationRiskLevel = "major" if entry_count >= 10 else "moderate"
    return [
        MedicationReviewFinding(
            finding_id="polypharmacy_10_or_more" if entry_count >= 10 else "polypharmacy_5_to_9",
            kind="polypharmacy",
            severity=severity,
            title=f"已录入 {entry_count} 种药物：多重用药核对提醒",
            involved_generic_names=("多重用药",),
            conclusion=(
                "已达到10种及以上药物的多重用药警示阈值。"
                if entry_count >= 10
                else "已达到5种及以上药物的多重用药提醒阈值。"
            ),
            clinician_action="请由医师或药师进行完整的药物核对、适应证和不良反应评估。",
            elderly_note="老年人多重用药时，药物相互作用和不良反应风险可能增加。",
        )
    ]


def _once_daily_milligrams(text: str) -> float | None:
    normalized = unicodedata.normalize("NFKC", text)
    if not _ONCE_DAILY.search(normalized):
        return None
    values = _MILLIGRAM.findall(normalized)
    if len(values) != 1:
        return None
    return float(values[0])


def _age_adjust(
    severity: MedicationRiskLevel, patient_age: int | None
) -> tuple[MedicationRiskLevel, bool]:
    if patient_age is not None and patient_age >= 75 and severity == "moderate":
        return "major", True
    return severity, False


def _severity_label(severity: MedicationRiskLevel) -> str:
    return {
        "contraindicated": "禁忌",
        "major": "严重",
        "moderate": "中等",
        "minor": "轻微",
    }[severity]


def _review_action(action: str) -> str:
    """Keep operational advice factual; the single final disclaimer carries patient risk."""

    return re.sub(r"[；，]患者不要自行[^。]*。?", "。", action)


def _conclusion(findings: list[MedicationReviewFinding]) -> str:
    if not findings:
        return (
            "在当前已安装的有限 DDI、剂量和 Beers 相关规则中未命中风险；"
            "这不代表用药方案安全或已完成完整 Beers 筛查。请由医师或药师完成完整核对。"
        )
    highest = _severity_label(findings[0].severity)
    return (
        f"本次依据已安装规则命中 {len(findings)} 项问题，最高等级为{highest}。"
        "所有结论均需由医师或药师结合病情、检验和原始处方复核。"
    )

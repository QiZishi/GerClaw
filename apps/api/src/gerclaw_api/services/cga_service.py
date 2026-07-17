"""Server-owned, deterministic CGA assessment state machines."""

from __future__ import annotations

import uuid
from typing import Any, Literal, cast

from gerclaw_api.database.models import CgaAssessment
from gerclaw_api.modules.cga.minicog import (
    MINICOG_FOLLOW_UP_MESSAGE,
    MINICOG_OPTIONS,
    MINICOG_QUESTIONS,
    MINICOG_SCALE_ID,
    MINICOG_VERSION,
    score_minicog,
)
from gerclaw_api.modules.cga.mmse import (
    MMSE_EDUCATION_ID,
    MMSE_EDUCATION_OPTIONS,
    MMSE_FOLLOW_UP_MESSAGE,
    MMSE_OPTIONS,
    MMSE_QUESTIONS,
    MMSE_SCALE_ID,
    MMSE_VERSION,
    score_mmse,
)
from gerclaw_api.modules.cga.models import (
    CgaActiveAssessmentsRead,
    CgaAssessmentRead,
    CgaComparisonRead,
    CgaHistoryItemRead,
    CgaHistoryRead,
    CgaQuestionRead,
    CgaReportRead,
    CgaRiskRead,
)
from gerclaw_api.modules.cga.phq9 import (
    HIGH_SCORE_SAFETY_MESSAGE,
    PHQ9_OPTIONS,
    PHQ9_QUESTIONS,
    PHQ9_SCALE_ID,
    PHQ9_VERSION,
    risk_for_answer,
    score_phq9,
)
from gerclaw_api.modules.cga.psqi import (
    PSQI_HIGH_SCORE_MESSAGE,
    PSQI_QUESTIONS,
    PSQI_SCALE_ID,
    PSQI_VERSION,
    psqi_options_for,
    score_psqi,
    validate_psqi_answer,
    validate_psqi_timing,
)
from gerclaw_api.modules.cga.sas import (
    SAS_HIGH_SCORE_MESSAGE,
    SAS_OPTIONS,
    SAS_QUESTIONS,
    SAS_SCALE_ID,
    SAS_VERSION,
    score_sas,
)
from gerclaw_api.repositories.cga import SqlAlchemyCgaRepository


class CgaAssessmentConflictError(RuntimeError):
    """The submitted state transition violates the server-owned workflow."""


class CgaService:
    def __init__(self, repository: SqlAlchemyCgaRepository) -> None:
        self._repository = repository

    async def start(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        scale_id: Literal["phq9", "sas", "psqi", "minicog", "mmse"] = "phq9",
    ) -> CgaAssessmentRead:
        version = {
            PHQ9_SCALE_ID: PHQ9_VERSION,
            SAS_SCALE_ID: SAS_VERSION,
            PSQI_SCALE_ID: PSQI_VERSION,
            MINICOG_SCALE_ID: MINICOG_VERSION,
            MMSE_SCALE_ID: MMSE_VERSION,
        }[scale_id]
        record = await self._repository.create(
            tenant_id=tenant_id,
            actor_id=actor_id,
            scale_id=scale_id,
            definition_version=version,
        )
        return self._read(record)

    async def get(
        self, assessment_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> CgaAssessmentRead:
        record = await self._repository.get(
            assessment_id, tenant_id=tenant_id, actor_id=actor_id
        )
        return self._read(record)

    async def answer(
        self,
        assessment_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        expected_revision: int,
        question_id: str,
        score: int,
        supplemental_detail: str | None = None,
    ) -> CgaAssessmentRead:
        record = await self._repository.lock(assessment_id, tenant_id=tenant_id, actor_id=actor_id)
        if record.status != "active":
            raise CgaAssessmentConflictError("completed assessments cannot accept more answers")
        answers = self._answers(record)
        detail = self._validate_supplemental_detail(
            record.scale_id, question_id, supplemental_detail
        )
        notes = self._notes(record)
        self._validate_score(record.scale_id, question_id, score)
        if question_id in answers:
            same_supplemental_detail = (
                supplemental_detail is None or notes.get(question_id) == detail
            )
            if answers[question_id] == score and same_supplemental_detail:
                return self._read(record)
            if record.revision != expected_revision:
                raise CgaAssessmentConflictError("assessment has changed; refresh before editing")
            answers[question_id] = score
            self._validate_candidate_answers(record.scale_id, answers)
            if record.scale_id == PHQ9_SCALE_ID:
                risk_for_answer(question_id, score)
            record.answers = answers
            record.notes = self._updated_notes(
                notes, question_id, detail, supplemental_detail is not None
            )
            record.revision += 1
            return self._read(record)
        if record.revision != expected_revision:
            raise CgaAssessmentConflictError("assessment has changed; refresh before answering")
        question = self._questions(record.scale_id)[record.current_position - 1]
        if question.id != question_id:
            raise CgaAssessmentConflictError(
                "answer must match the server-provided current question"
            )
        answers[question_id] = score
        self._validate_candidate_answers(record.scale_id, answers)
        if record.scale_id == PHQ9_SCALE_ID:
            risk_for_answer(question_id, score)
        record.answers = answers
        record.notes = self._updated_notes(
            notes, question_id, detail, supplemental_detail is not None
        )
        if record.current_position < len(self._questions(record.scale_id)):
            record.current_position += 1
        record.revision += 1
        return self._read(record)

    async def complete(
        self, assessment_id: uuid.UUID, *, tenant_id: str, actor_id: str, expected_revision: int
    ) -> CgaAssessmentRead:
        record = await self._repository.lock(assessment_id, tenant_id=tenant_id, actor_id=actor_id)
        if record.status != "active" or record.revision != expected_revision:
            raise CgaAssessmentConflictError("assessment has changed; refresh before completing")
        try:
            report = self._report(record)
        except ValueError as error:
            raise CgaAssessmentConflictError(
                "all server-defined assessment answers are required before completing"
            ) from error
        record.status = "completed"
        record.report = report.model_dump(mode="json")
        record.revision += 1
        return self._read(record)

    async def report(
        self, assessment_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> CgaReportRead:
        record = await self._repository.get(
            assessment_id, tenant_id=tenant_id, actor_id=actor_id
        )
        if record.status != "completed" or record.report is None:
            raise CgaAssessmentConflictError("assessment report is not available")
        return CgaReportRead.model_validate(record.report)

    async def history(
        self, *, tenant_id: str, actor_id: str, limit: int
    ) -> CgaHistoryRead:
        """List bounded, caller-owned completed reports without exposing answers."""

        records = await self._repository.list_completed(
            tenant_id=tenant_id, actor_id=actor_id, limit=limit
        )
        items: list[CgaHistoryItemRead] = []
        for record in records:
            items.append(self._history_item(record))
        return CgaHistoryRead(items=items)

    async def comparison(
        self, assessment_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> CgaComparisonRead:
        """Compare only equivalent completed, caller-owned screening versions.

        The result deliberately describes a numerical difference only.  It is
        not an interpretation of symptom change, diagnosis, or treatment need.
        """

        current_record = await self._repository.get(
            assessment_id, tenant_id=tenant_id, actor_id=actor_id
        )
        if current_record.status != "completed":
            raise CgaAssessmentConflictError("assessment report is not available")
        current = self._history_item(current_record)
        prior_record = await self._repository.previous_completed_same_scale(
            current_record, tenant_id=tenant_id, actor_id=actor_id
        )
        if prior_record is None:
            return CgaComparisonRead(
                status="no_prior_same_scale",
                current=current,
                disclaimer="暂无可对照的同量表历史结果。筛查分数不能替代医生诊断。",
            )
        prior = self._history_item(prior_record)
        if prior.definition_version != current.definition_version:
            return CgaComparisonRead(
                status="definition_version_changed",
                current=current,
                prior=prior,
                disclaimer="两次量表版本不同, 系统未比较分数。筛查分数不能替代医生诊断。",
            )
        return CgaComparisonRead(
            status="comparable",
            current=current,
            prior=prior,
            score_delta=current.report.total_score - prior.report.total_score,
            disclaimer=(
                "分数变化仅供回顾同一量表的两次筛查结果, 不等于病情诊断或治疗建议; "
                "请结合医生评估。"
            ),
        )

    async def active(
        self, *, tenant_id: str, actor_id: str, limit: int
    ) -> CgaActiveAssessmentsRead:
        """List the caller's resumable server-owned states without raw answers."""

        records = await self._repository.list_active(
            tenant_id=tenant_id, actor_id=actor_id, limit=limit
        )
        newest_by_scale: list[CgaAssessmentRead] = []
        seen_scales: set[str] = set()
        for record in records:
            if record.scale_id in seen_scales:
                continue
            seen_scales.add(record.scale_id)
            newest_by_scale.append(self._read(record))
            if len(newest_by_scale) == 5:
                break
        return CgaActiveAssessmentsRead(items=newest_by_scale)

    def _read(self, record: CgaAssessment) -> CgaAssessmentRead:
        answers = self._answers(record)
        report = record.report or {}
        messages = (
            risk_for_answer("phq9_9", answers.get("phq9_9", 0))
            if record.scale_id == PHQ9_SCALE_ID
            else ()
        )
        high_follow_up = report.get("high_severity_follow_up") is True
        high_score_message = {
            PHQ9_SCALE_ID: HIGH_SCORE_SAFETY_MESSAGE,
            SAS_SCALE_ID: SAS_HIGH_SCORE_MESSAGE,
            PSQI_SCALE_ID: PSQI_HIGH_SCORE_MESSAGE,
            MINICOG_SCALE_ID: MINICOG_FOLLOW_UP_MESSAGE,
            MMSE_SCALE_ID: MMSE_FOLLOW_UP_MESSAGE,
        }.get(record.scale_id)
        if high_score_message is None:
            raise CgaAssessmentConflictError("assessment uses an unsupported scale")
        if high_follow_up and high_score_message not in messages:
            messages += (high_score_message,)
        next_question = None
        if record.status == "active" and len(answers) < len(self._questions(record.scale_id)):
            next_question = self._question(record.scale_id, record.current_position)
        return CgaAssessmentRead(
            assessment_id=record.id,
            scale_id=cast(Literal["phq9", "sas", "psqi", "minicog", "mmse"], record.scale_id),
            definition_version=record.definition_version,
            status=cast(Literal["active", "completed", "abandoned"], record.status),
            revision=record.revision,
            answered_count=len(answers),
            next_question=next_question,
            risk=CgaRiskRead(
                requires_immediate_safety_assessment=(
                    record.scale_id == PHQ9_SCALE_ID and answers.get("phq9_9", 0) > 0
                ),
                high_severity_follow_up=high_follow_up,
                messages=list(messages),
            ),
        )

    @staticmethod
    def _history_item(record: CgaAssessment) -> CgaHistoryItemRead:
        if record.report is None or record.updated_at is None:
            raise CgaAssessmentConflictError("completed assessment state is invalid")
        try:
            report = CgaReportRead.model_validate(record.report)
        except ValueError as error:
            raise CgaAssessmentConflictError("completed assessment report is invalid") from error
        return CgaHistoryItemRead(
            assessment_id=record.id,
            scale_id=cast(Literal["phq9", "sas", "psqi", "minicog", "mmse"], record.scale_id),
            definition_version=record.definition_version,
            completed_at=record.updated_at,
            report=report,
        )

    @staticmethod
    def _question(scale_id: str, position: int) -> CgaQuestionRead:
        question = CgaService._questions(scale_id)[position - 1]
        return CgaQuestionRead(
            id=question.id,
            position=question.position,
            text=question.text,
            sensitive_prefix=getattr(question, "sensitive_prefix", None),
            input_kind=getattr(question, "input_kind", "ordinal"),
            options=list(CgaService._options(scale_id, question.id)),
        )

    @staticmethod
    def _questions(scale_id: str) -> tuple[Any, ...]:
        if scale_id == PHQ9_SCALE_ID:
            return PHQ9_QUESTIONS
        if scale_id == SAS_SCALE_ID:
            return SAS_QUESTIONS
        if scale_id == PSQI_SCALE_ID:
            return PSQI_QUESTIONS
        if scale_id == MINICOG_SCALE_ID:
            return MINICOG_QUESTIONS
        if scale_id == MMSE_SCALE_ID:
            return MMSE_QUESTIONS
        raise CgaAssessmentConflictError("assessment uses an unsupported scale")

    @staticmethod
    def _options(scale_id: str, question_id: str) -> tuple[tuple[int, str], ...]:
        if scale_id == PHQ9_SCALE_ID:
            return PHQ9_OPTIONS
        if scale_id == SAS_SCALE_ID:
            return SAS_OPTIONS
        if scale_id == PSQI_SCALE_ID:
            try:
                return psqi_options_for(question_id)
            except ValueError as error:
                raise CgaAssessmentConflictError(
                    "assessment uses an unsupported question"
                ) from error
        if scale_id == MINICOG_SCALE_ID:
            return MINICOG_OPTIONS[question_id]
        if scale_id == MMSE_SCALE_ID:
            return MMSE_EDUCATION_OPTIONS if question_id == MMSE_EDUCATION_ID else MMSE_OPTIONS
        raise CgaAssessmentConflictError("assessment uses an unsupported scale")

    @classmethod
    def _validate_score(cls, scale_id: str, question_id: str, score: int) -> None:
        if scale_id == PSQI_SCALE_ID:
            try:
                validate_psqi_answer(question_id, score)
            except ValueError as error:
                raise CgaAssessmentConflictError(
                    "answer score is invalid for this server-defined question"
                ) from error
            return
        if scale_id == MMSE_SCALE_ID and question_id == MMSE_EDUCATION_ID:
            education_scores = {value for value, _ in MMSE_EDUCATION_OPTIONS}
            if isinstance(score, bool) or score not in education_scores:
                raise CgaAssessmentConflictError(
                    "answer score is invalid for this server-defined question"
                )
            return
        valid_scores = {value for value, _label in cls._options(scale_id, question_id)}
        if isinstance(score, bool) or score not in valid_scores:
            raise CgaAssessmentConflictError(
                "answer score is invalid for this server-defined question"
            )

    @staticmethod
    def _validate_candidate_answers(scale_id: str, answers: dict[str, int]) -> None:
        if scale_id != PSQI_SCALE_ID:
            return
        try:
            validate_psqi_timing(answers)
        except ValueError as error:
            raise CgaAssessmentConflictError(
                "answer is inconsistent with previously saved assessment answers"
            ) from error

    def _report(self, record: CgaAssessment) -> CgaReportRead:
        if record.scale_id == PHQ9_SCALE_ID:
            phq9_result = score_phq9(self._answers(record))
            return CgaReportRead(
                total_score=phq9_result.total_score,
                score_max=27,
                severity=phq9_result.severity,
                self_harm_signal=phq9_result.self_harm_signal,
                requires_immediate_safety_assessment=phq9_result.requires_immediate_safety_assessment,
                high_severity_follow_up=phq9_result.high_severity_follow_up,
                safety_messages=list(phq9_result.safety_messages),
                disclaimer=phq9_result.disclaimer,
            )
        if record.scale_id == SAS_SCALE_ID:
            sas_result = score_sas(self._answers(record))
            return CgaReportRead(
                total_score=sas_result.standard_score,
                score_max=100,
                raw_score=sas_result.raw_score,
                standard_score=sas_result.standard_score,
                severity=sas_result.severity,
                high_severity_follow_up=sas_result.high_severity_follow_up,
                safety_messages=list(sas_result.safety_messages),
                disclaimer=sas_result.disclaimer,
            )
        if record.scale_id == PSQI_SCALE_ID:
            psqi_result = score_psqi(self._answers(record))
            return CgaReportRead(
                total_score=psqi_result.total_score,
                score_max=21,
                severity=psqi_result.severity,
                high_severity_follow_up=psqi_result.high_severity_follow_up,
                safety_messages=list(psqi_result.safety_messages),
                component_scores=psqi_result.component_scores,
                disclaimer=psqi_result.disclaimer,
            )
        if record.scale_id == MINICOG_SCALE_ID:
            answers = self._answers(record)
            minicog_result = score_minicog(
                recalled_word_count=answers["minicog_recall"],
                reported_clock_score=answers["minicog_clock"],
            )
            return CgaReportRead(
                total_score=minicog_result.total_score,
                score_max=5,
                severity=minicog_result.severity,
                high_severity_follow_up=minicog_result.high_severity_follow_up,
                safety_messages=list(minicog_result.safety_messages),
                component_scores={
                    "word_recall": minicog_result.recalled_word_count,
                    "clock_task_self_report": minicog_result.reported_clock_score,
                },
                disclaimer=minicog_result.disclaimer,
            )
        if record.scale_id == MMSE_SCALE_ID:
            answers = self._answers(record)
            education_level = {
                0: "none",
                1: "primary_or_less",
                2: "secondary_or_more",
            }[answers[MMSE_EDUCATION_ID]]
            mmse_result = score_mmse(
                reported_item_scores={
                    item_id: answers[item_id]
                    for item_id in answers
                    if item_id != MMSE_EDUCATION_ID
                },
                education_level=cast(
                    Literal["none", "primary_or_less", "secondary_or_more"], education_level
                ),
            )
            return CgaReportRead(
                total_score=mmse_result.total_score,
                score_max=30,
                severity=mmse_result.severity,
                education_level=mmse_result.education_level,
                education_threshold=mmse_result.education_threshold,
                education_adjusted_screen_positive=mmse_result.education_adjusted_screen_positive,
                high_severity_follow_up=mmse_result.high_severity_follow_up,
                safety_messages=list(mmse_result.safety_messages),
                component_scores={
                    "orientation": sum(
                        answers[f"mmse_{position}"] for position in range(1, 11)
                    ),
                    "immediate_memory": sum(
                        answers[f"mmse_{position}"] for position in range(11, 14)
                    ),
                    "attention_calculation": sum(
                        answers[f"mmse_{position}"] for position in range(14, 19)
                    ),
                    "recall": sum(
                        answers[f"mmse_{position}"] for position in range(19, 22)
                    ),
                    "language_and_tasks": sum(
                        answers[f"mmse_{position}"] for position in range(22, 31)
                    ),
                },
                disclaimer=(
                    "本结果基于本人作答的认知筛查, 不能替代医生的临床诊断。"
                ),
            )
        raise CgaAssessmentConflictError("assessment uses an unsupported scale")

    @staticmethod
    def _answers(record: CgaAssessment) -> dict[str, int]:
        values: dict[str, Any] = record.answers
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values.values()):
            raise CgaAssessmentConflictError("stored assessment state is invalid")
        return dict(values)

    @staticmethod
    def _notes(record: CgaAssessment) -> dict[str, str]:
        if record.notes is None:
            return {}
        if not isinstance(record.notes, dict):
            raise CgaAssessmentConflictError("stored supplemental assessment detail is invalid")
        values: dict[str, Any] = record.notes
        if (
            set(values) - {"psqi_5j"}
            or any(
                not isinstance(value, str) or not value.strip() or len(value) > 500
                for value in values.values()
            )
        ):
            raise CgaAssessmentConflictError("stored supplemental assessment detail is invalid")
        return dict(values)

    @staticmethod
    def _validate_supplemental_detail(
        scale_id: str, question_id: str, supplemental_detail: str | None
    ) -> str | None:
        if supplemental_detail is None:
            return None
        if scale_id != PSQI_SCALE_ID or question_id != "psqi_5j":
            raise CgaAssessmentConflictError(
                "supplemental detail is only permitted for PSQI item 5J"
            )
        detail = supplemental_detail.strip()
        if len(detail) > 500:
            raise CgaAssessmentConflictError("supplemental detail is too long")
        return detail or None

    @staticmethod
    def _updated_notes(
        notes: dict[str, str],
        question_id: str,
        detail: str | None,
        detail_was_submitted: bool,
    ) -> dict[str, str]:
        if question_id != "psqi_5j" or not detail_was_submitted:
            return notes
        if detail is None:
            return {}
        return {"psqi_5j": detail}

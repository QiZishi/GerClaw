"""Server-owned, deterministic CGA assessment state machines."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from gerclaw_api.database.models import CgaAssessment
from gerclaw_api.modules.cga.models import (
    CgaAssessmentRead,
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
        scale_id: Literal["phq9", "sas", "psqi"] = "phq9",
    ) -> CgaAssessmentRead:
        version = {
            PHQ9_SCALE_ID: PHQ9_VERSION,
            SAS_SCALE_ID: SAS_VERSION,
            PSQI_SCALE_ID: PSQI_VERSION,
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
    ) -> CgaAssessmentRead:
        record = await self._repository.lock(assessment_id, tenant_id=tenant_id, actor_id=actor_id)
        if record.status != "active":
            raise CgaAssessmentConflictError("completed assessments cannot accept more answers")
        answers = self._answers(record)
        self._validate_score(record.scale_id, question_id, score)
        if question_id in answers:
            if answers[question_id] == score:
                return self._read(record)
            if record.revision != expected_revision:
                raise CgaAssessmentConflictError("assessment has changed; refresh before editing")
            answers[question_id] = score
            self._validate_candidate_answers(record.scale_id, answers)
            if record.scale_id == PHQ9_SCALE_ID:
                risk_for_answer(question_id, score)
            record.answers = answers
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
            scale_id=record.scale_id,
            definition_version=record.definition_version,
            status=record.status,
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
        raise CgaAssessmentConflictError("assessment uses an unsupported scale")

    @staticmethod
    def _answers(record: CgaAssessment) -> dict[str, int]:
        values: dict[str, Any] = record.answers
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values.values()):
            raise CgaAssessmentConflictError("stored assessment state is invalid")
        return dict(values)

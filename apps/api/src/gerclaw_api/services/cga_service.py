"""Server-owned PHQ-9 assessment state machine."""

from __future__ import annotations

import uuid
from typing import Any

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
from gerclaw_api.repositories.cga import SqlAlchemyCgaRepository


class CgaAssessmentConflictError(RuntimeError):
    """The submitted state transition violates the server-owned workflow."""


class CgaService:
    def __init__(self, repository: SqlAlchemyCgaRepository) -> None:
        self._repository = repository

    async def start(self, *, tenant_id: str, actor_id: str) -> CgaAssessmentRead:
        record = await self._repository.create(
            tenant_id=tenant_id,
            actor_id=actor_id,
            scale_id=PHQ9_SCALE_ID,
            definition_version=PHQ9_VERSION,
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
        if record.status != "active" or record.revision != expected_revision:
            raise CgaAssessmentConflictError("assessment has changed; refresh before answering")
        question = PHQ9_QUESTIONS[record.current_position - 1]
        if question.id != question_id:
            raise CgaAssessmentConflictError(
                "answer must match the server-provided current question"
            )
        answers = self._answers(record)
        answers[question_id] = score
        risk_for_answer(question_id, score)
        record.answers = answers
        if record.current_position < len(PHQ9_QUESTIONS):
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
            result = score_phq9(self._answers(record))
        except ValueError as error:
            raise CgaAssessmentConflictError(
                "all server-defined PHQ-9 answers are required before completing"
            ) from error
        record.status = "completed"
        record.report = CgaReportRead(
            total_score=result.total_score,
            severity=result.severity,
            self_harm_signal=result.self_harm_signal,
            requires_immediate_safety_assessment=result.requires_immediate_safety_assessment,
            high_severity_follow_up=result.high_severity_follow_up,
            safety_messages=list(result.safety_messages),
            disclaimer=result.disclaimer,
        ).model_dump(mode="json")
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
        messages = risk_for_answer("phq9_9", answers.get("phq9_9", 0))
        high_follow_up = report.get("high_severity_follow_up") is True
        if high_follow_up and HIGH_SCORE_SAFETY_MESSAGE not in messages:
            messages += (HIGH_SCORE_SAFETY_MESSAGE,)
        next_question = None
        if record.status == "active" and len(answers) < len(PHQ9_QUESTIONS):
            next_question = self._question(record.current_position)
        return CgaAssessmentRead(
            assessment_id=record.id,
            scale_id="phq9",
            definition_version=record.definition_version,
            status=record.status,
            revision=record.revision,
            answered_count=len(answers),
            next_question=next_question,
            risk=CgaRiskRead(
                requires_immediate_safety_assessment=bool(messages and answers.get("phq9_9", 0)),
                high_severity_follow_up=high_follow_up,
                messages=list(messages),
            ),
        )

    @staticmethod
    def _question(position: int) -> CgaQuestionRead:
        question = PHQ9_QUESTIONS[position - 1]
        return CgaQuestionRead(
            id=question.id,
            position=question.position,
            text=question.text,
            sensitive_prefix=question.sensitive_prefix,
            options=list(PHQ9_OPTIONS),
        )

    @staticmethod
    def _answers(record: CgaAssessment) -> dict[str, int]:
        values: dict[str, Any] = record.answers
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values.values()):
            raise CgaAssessmentConflictError("stored assessment state is invalid")
        return dict(values)

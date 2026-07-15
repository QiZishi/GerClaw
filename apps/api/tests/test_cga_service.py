"""State-machine tests for the deterministic, server-owned PHQ-9 workflow."""

import uuid

import pytest

from gerclaw_api.database.models import CgaAssessment
from gerclaw_api.modules.cga.phq9 import PHQ9_QUESTIONS
from gerclaw_api.services.cga_service import CgaAssessmentConflictError, CgaService


class _Repository:
    def __init__(self) -> None:
        self.record: CgaAssessment | None = None

    async def create(self, **kwargs: str) -> CgaAssessment:
        self.record = CgaAssessment(
            id=uuid.uuid4(),
            status="active",
            current_position=1,
            revision=1,
            **kwargs,
            answers={},
        )
        return self.record

    async def get(self, assessment_id: uuid.UUID, **_kwargs: str) -> CgaAssessment:
        assert self.record is not None and self.record.id == assessment_id
        return self.record

    async def lock(self, assessment_id: uuid.UUID, **_kwargs: str) -> CgaAssessment:
        return await self.get(assessment_id)


@pytest.mark.asyncio
async def test_phq9_state_machine_rejects_skips_and_preserves_resume_position() -> None:
    service = CgaService(_Repository())  # type: ignore[arg-type]
    started = await service.start(tenant_id="tenant_public0001", actor_id="usr_patient_test0001")

    assert started.next_question is not None
    assert started.next_question.id == "phq9_1"
    with pytest.raises(CgaAssessmentConflictError):
        await service.answer(
            started.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=started.revision,
            question_id="phq9_2",
            score=0,
        )

    answered = await service.answer(
        started.assessment_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
        expected_revision=started.revision,
        question_id="phq9_1",
        score=0,
    )
    resumed = await service.get(
        started.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )
    assert answered.answered_count == 1
    assert resumed.next_question is not None and resumed.next_question.id == "phq9_2"


@pytest.mark.asyncio
async def test_phq9_item_nine_signal_and_completion_report_are_server_calculated() -> None:
    service = CgaService(_Repository())  # type: ignore[arg-type]
    state = await service.start(tenant_id="tenant_public0001", actor_id="usr_patient_test0001")

    for question in PHQ9_QUESTIONS:
        state = await service.answer(
            state.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=state.revision,
            question_id=question.id,
            score=1 if question.id == "phq9_9" else 0,
        )
    assert state.risk.requires_immediate_safety_assessment is True
    assert state.next_question is None
    completed = await service.complete(
        state.assessment_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
        expected_revision=state.revision,
    )
    assert completed.status == "completed"
    assert completed.next_question is None
    report = await service.report(
        state.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )
    assert report.self_harm_signal is True
    assert report.requires_immediate_safety_assessment is True

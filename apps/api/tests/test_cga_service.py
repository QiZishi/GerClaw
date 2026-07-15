"""State-machine tests for the deterministic, server-owned PHQ-9 workflow."""

import uuid

import pytest

from gerclaw_api.database.models import CgaAssessment
from gerclaw_api.modules.cga.phq9 import PHQ9_QUESTIONS
from gerclaw_api.modules.cga.psqi import PSQI_QUESTIONS
from gerclaw_api.modules.cga.sas import SAS_QUESTIONS
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

    replayed = await service.answer(
        started.assessment_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
        expected_revision=started.revision,
        question_id="phq9_1",
        score=0,
    )
    assert replayed.revision == answered.revision
    edited = await service.answer(
        started.assessment_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
        expected_revision=answered.revision,
        question_id="phq9_1",
        score=2,
    )
    assert edited.revision == answered.revision + 1
    assert edited.answered_count == 1


@pytest.mark.asyncio
async def test_phq9_cannot_complete_before_all_server_defined_answers_exist() -> None:
    service = CgaService(_Repository())  # type: ignore[arg-type]
    started = await service.start(tenant_id="tenant_public0001", actor_id="usr_patient_test0001")

    with pytest.raises(CgaAssessmentConflictError):
        await service.complete(
            started.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=started.revision,
        )
    unchanged = await service.get(
        started.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )
    assert unchanged.status == "active"
    assert unchanged.revision == started.revision


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
    with pytest.raises(CgaAssessmentConflictError):
        await service.answer(
            state.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=completed.revision,
            question_id="phq9_9",
            score=1,
        )
    unchanged = await service.get(
        state.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )
    assert unchanged.revision == completed.revision
    report = await service.report(
        state.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )
    assert report.self_harm_signal is True
    assert report.requires_immediate_safety_assessment is True


@pytest.mark.asyncio
async def test_sas_state_machine_uses_server_order_and_persists_standard_score() -> None:
    service = CgaService(_Repository())  # type: ignore[arg-type]
    state = await service.start(
        tenant_id="tenant_public0001", actor_id="usr_patient_test0001", scale_id="sas"
    )

    assert state.scale_id == "sas"
    assert state.next_question is not None and state.next_question.id == "sas_1"
    assert state.next_question.options[0][0] == 1
    for question in SAS_QUESTIONS:
        state = await service.answer(
            state.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=state.revision,
            question_id=question.id,
            score=1 if question.reverse_scored else 4,
        )
    completed = await service.complete(
        state.assessment_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
        expected_revision=state.revision,
    )
    assert completed.status == "completed"
    report = await service.report(
        state.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )
    assert report.raw_score == 80
    assert report.standard_score == 100
    assert report.total_score == 100
    assert report.score_max == 100
    assert report.requires_immediate_safety_assessment is False


@pytest.mark.asyncio
async def test_legacy_phq9_report_remains_readable_after_multiscale_contract_change() -> None:
    repository = _Repository()
    service = CgaService(repository)  # type: ignore[arg-type]
    state = await service.start(tenant_id="tenant_public0001", actor_id="usr_patient_test0001")
    assert repository.record is not None
    repository.record.status = "completed"
    repository.record.report = {
        "total_score": 4,
        "severity": "minimal",
        "self_harm_signal": False,
        "requires_immediate_safety_assessment": False,
        "high_severity_follow_up": False,
        "safety_messages": [],
        "disclaimer": "筛查结果不能替代临床诊断。",
    }

    report = await service.report(
        state.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )

    assert report.score_max == 27
    assert report.raw_score is None
    assert report.standard_score is None


@pytest.mark.asyncio
async def test_psqi_state_machine_accepts_only_server_defined_mixed_numeric_answers() -> None:
    service = CgaService(_Repository())  # type: ignore[arg-type]
    state = await service.start(
        tenant_id="tenant_public0001", actor_id="usr_patient_test0001", scale_id="psqi"
    )

    assert state.next_question is not None
    assert state.next_question.id == "psqi_1"
    assert state.next_question.input_kind == "clock_minutes"
    with pytest.raises(CgaAssessmentConflictError):
        await service.answer(
            state.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=state.revision,
            question_id="psqi_1",
            score=1_440,
        )

    answer_by_id = {"psqi_1": 23 * 60, "psqi_3": 7 * 60, "psqi_4": 8 * 60}
    for question in PSQI_QUESTIONS:
        state = await service.answer(
            state.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=state.revision,
            question_id=question.id,
            score=answer_by_id.get(question.id, 0),
        )
    completed = await service.complete(
        state.assessment_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
        expected_revision=state.revision,
    )
    report = await service.report(
        state.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )

    assert completed.status == "completed"
    assert report.total_score == 0
    assert report.score_max == 21
    assert report.component_scores["sleep_efficiency"] == 0


@pytest.mark.asyncio
async def test_psqi_rejects_impossible_sleep_duration_before_persisting_it() -> None:
    service = CgaService(_Repository())  # type: ignore[arg-type]
    state = await service.start(
        tenant_id="tenant_public0001", actor_id="usr_patient_test0001", scale_id="psqi"
    )
    for question_id, score in (("psqi_1", 23 * 60), ("psqi_2", 0), ("psqi_3", 7 * 60)):
        state = await service.answer(
            state.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=state.revision,
            question_id=question_id,
            score=score,
        )

    with pytest.raises(CgaAssessmentConflictError):
        await service.answer(
            state.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=state.revision,
            question_id="psqi_4",
            score=9 * 60,
        )

    resumed = await service.get(
        state.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )
    assert resumed.revision == state.revision
    assert resumed.next_question is not None and resumed.next_question.id == "psqi_4"

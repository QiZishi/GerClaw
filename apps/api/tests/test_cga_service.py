"""State-machine tests for the deterministic, server-owned PHQ-9 workflow."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from gerclaw_api.database.models import CgaAssessment
from gerclaw_api.modules.cga.minicog import MINICOG_QUESTIONS
from gerclaw_api.modules.cga.mmse import MMSE_QUESTIONS
from gerclaw_api.modules.cga.models import CgaAnswerRequest
from gerclaw_api.modules.cga.phq9 import PHQ9_QUESTIONS
from gerclaw_api.modules.cga.psqi import PSQI_QUESTIONS
from gerclaw_api.modules.cga.sas import SAS_QUESTIONS
from gerclaw_api.services.cga_service import CgaAssessmentConflictError, CgaService


@pytest.mark.asyncio
async def test_minicog_self_report_workflow_scores_and_marks_follow_up() -> None:
    service = CgaService(_Repository())  # type: ignore[arg-type]
    state = await service.start(
        tenant_id="tenant_public0001", actor_id="usr_patient_test0001", scale_id="minicog"
    )

    assert state.next_question is not None and state.next_question.id == "minicog_prepare"
    for question, score in zip(MINICOG_QUESTIONS, (0, 0, 2), strict=True):
        state = await service.answer(
            state.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=state.revision,
            question_id=question.id,
            score=score,
        )
    completed = await service.complete(
        state.assessment_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
        expected_revision=state.revision,
    )
    report = await service.report(
        completed.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )

    assert report.total_score == 2
    assert report.score_max == 5
    assert report.severity == "possible_impairment"
    assert report.high_severity_follow_up is True
    assert "clock_task_self_report" in report.component_scores


@pytest.mark.asyncio
async def test_mmse_self_report_workflow_uses_education_adjusted_threshold() -> None:
    service = CgaService(_Repository())  # type: ignore[arg-type]
    state = await service.start(
        tenant_id="tenant_public0001", actor_id="usr_patient_test0001", scale_id="mmse"
    )

    assert len(MMSE_QUESTIONS) == 31
    for question in MMSE_QUESTIONS:
        score = 2 if question.id == "mmse_education" else 1
        state = await service.answer(
            state.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=state.revision,
            question_id=question.id,
            score=score,
        )
    completed = await service.complete(
        state.assessment_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
        expected_revision=state.revision,
    )
    report = await service.report(
        completed.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )

    assert report.total_score == 30
    assert report.score_max == 30
    assert report.severity == "normal"
    assert report.education_level == "secondary_or_more"
    assert report.education_threshold == 24
    assert report.education_adjusted_screen_positive is False


class _Repository:
    def __init__(self) -> None:
        self.record: CgaAssessment | None = None
        self.history_records: list[CgaAssessment] = []
        self.active_records: list[CgaAssessment] = []
        self.prior_completed_record: CgaAssessment | None = None

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

    async def list_completed(self, **_kwargs: object) -> list[CgaAssessment]:
        return self.history_records

    async def list_active(self, **_kwargs: object) -> list[CgaAssessment]:
        return self.active_records

    async def previous_completed_same_scale(
        self, _record: CgaAssessment, **_kwargs: str
    ) -> CgaAssessment | None:
        return self.prior_completed_record


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
async def test_active_list_exposes_only_resumable_read_models() -> None:
    repository = _Repository()
    service = CgaService(repository)  # type: ignore[arg-type]
    started = await service.start(tenant_id="tenant_public0001", actor_id="usr_patient_test0001")
    repository.active_records = [repository.record] if repository.record is not None else []

    active = await service.active(
        tenant_id="tenant_public0001", actor_id="usr_patient_test0001", limit=3
    )

    assert [item.assessment_id for item in active.items] == [started.assessment_id]
    assert active.items[0].status == "active"
    assert active.items[0].next_question is not None


@pytest.mark.asyncio
async def test_active_list_keeps_only_the_newest_state_per_scale() -> None:
    repository = _Repository()
    service = CgaService(repository)  # type: ignore[arg-type]
    older = await service.start(tenant_id="tenant_public0001", actor_id="usr_patient_test0001")
    newer = await service.start(tenant_id="tenant_public0001", actor_id="usr_patient_test0001")
    assert repository.record is not None
    repository.record.answers = {"phq9_1": 0}
    repository.record.current_position = 2
    repository.active_records = [
        repository.record,
        CgaAssessment(
            id=older.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            scale_id="phq9",
            definition_version="phq9-v1",
            status="active",
            current_position=1,
            revision=1,
            answers={},
            notes={},
        ),
    ]

    active = await service.active(
        tenant_id="tenant_public0001", actor_id="usr_patient_test0001", limit=20
    )

    assert [item.assessment_id for item in active.items] == [newer.assessment_id]
    assert active.items[0].next_question is not None
    assert active.items[0].next_question.id == "phq9_2"


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
async def test_history_returns_only_completed_report_summaries_without_answers() -> None:
    repository = _Repository()
    service = CgaService(repository)  # type: ignore[arg-type]
    state = await service.start(tenant_id="tenant_public0001", actor_id="usr_patient_test0001")
    assert repository.record is not None
    repository.record.status = "completed"
    repository.record.updated_at = datetime(2026, 7, 16, tzinfo=UTC)
    repository.record.answers = {"phq9_1": 3}
    repository.record.report = {
        "total_score": 3,
        "score_max": 27,
        "severity": "minimal",
        "self_harm_signal": False,
        "requires_immediate_safety_assessment": False,
        "high_severity_follow_up": False,
        "safety_messages": [],
        "component_scores": {},
        "disclaimer": "筛查结果不能替代临床诊断。",
    }
    repository.history_records = [repository.record]

    history = await service.history(
        tenant_id="tenant_public0001", actor_id="usr_patient_test0001", limit=10
    )

    assert len(history.items) == 1
    assert history.items[0].assessment_id == state.assessment_id
    assert history.items[0].report.total_score == 3
    assert "answers" not in history.items[0].model_dump(mode="json")


@pytest.mark.asyncio
async def test_comparison_is_owner_scoped_and_only_calculates_same_definition_versions() -> None:
    repository = _Repository()
    service = CgaService(repository)  # type: ignore[arg-type]
    current = await service.start(tenant_id="tenant_public0001", actor_id="usr_patient_test0001")
    assert repository.record is not None
    repository.record.status = "completed"
    repository.record.updated_at = datetime(2026, 7, 16, tzinfo=UTC)
    repository.record.report = {
        "total_score": 7,
        "score_max": 27,
        "severity": "mild",
        "self_harm_signal": False,
        "requires_immediate_safety_assessment": False,
        "high_severity_follow_up": False,
        "safety_messages": [],
        "component_scores": {},
        "disclaimer": "筛查结果不能替代临床诊断。",
    }
    repository.prior_completed_record = CgaAssessment(
        id=uuid.uuid4(),
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
        scale_id="phq9",
        definition_version=repository.record.definition_version,
        status="completed",
        current_position=9,
        revision=10,
        answers={},
        notes={},
        updated_at=datetime(2026, 7, 15, tzinfo=UTC),
        report={
            "total_score": 4,
            "score_max": 27,
            "severity": "minimal",
            "self_harm_signal": False,
            "requires_immediate_safety_assessment": False,
            "high_severity_follow_up": False,
            "safety_messages": [],
            "component_scores": {},
            "disclaimer": "筛查结果不能替代临床诊断。",
        },
    )

    comparable = await service.comparison(
        current.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )

    assert comparable.status == "comparable"
    assert comparable.score_delta == 3
    assert "诊断" in comparable.disclaimer
    assert comparable.prior is not None

    repository.prior_completed_record.definition_version = "phq9-v2"
    version_changed = await service.comparison(
        current.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )
    assert version_changed.status == "definition_version_changed"
    assert version_changed.score_delta is None

    repository.prior_completed_record = None
    no_prior = await service.comparison(
        current.assessment_id, tenant_id="tenant_public0001", actor_id="usr_patient_test0001"
    )
    assert no_prior.status == "no_prior_same_scale"
    assert no_prior.prior is None


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


@pytest.mark.asyncio
async def test_psqi_5j_supplemental_detail_is_separate_from_score_or_report_data() -> None:
    repository = _Repository()
    service = CgaService(repository)  # type: ignore[arg-type]
    state = await service.start(
        tenant_id="tenant_public0001", actor_id="usr_patient_test0001", scale_id="psqi"
    )
    for question in PSQI_QUESTIONS:
        if question.id == "psqi_5j":
            break
        state = await service.answer(
            state.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=state.revision,
            question_id=question.id,
            score={"psqi_1": 23 * 60, "psqi_3": 7 * 60, "psqi_4": 8 * 60}.get(question.id, 0),
        )

    state = await service.answer(
        state.assessment_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
        expected_revision=state.revision,
        question_id="psqi_5j",
        score=2,
        supplemental_detail="夜间施工噪声",
    )
    assert repository.record is not None
    assert repository.record.notes == {"psqi_5j": "夜间施工噪声"}
    assert state.next_question is not None and state.next_question.id == "psqi_6"

    replayed = await service.answer(
        state.assessment_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
        expected_revision=state.revision,
        question_id="psqi_5j",
        score=2,
    )
    assert replayed.revision == state.revision
    assert repository.record.notes == {"psqi_5j": "夜间施工噪声"}

    with pytest.raises(CgaAssessmentConflictError):
        await service.answer(
            state.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=state.revision,
            question_id="psqi_6",
            score=0,
            supplemental_detail="不得附加到其他题目",
        )

    for question in PSQI_QUESTIONS:
        if question.position <= 14:
            continue
        state = await service.answer(
            state.assessment_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_test0001",
            expected_revision=state.revision,
            question_id=question.id,
            score=0,
        )
    completed = await service.complete(
        state.assessment_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
        expected_revision=state.revision,
    )
    report = await service.report(
        completed.assessment_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_test0001",
    )
    assert "夜间施工噪声" not in report.model_dump_json()

    repository.record.updated_at = datetime(2026, 7, 16, tzinfo=UTC)
    repository.history_records = [repository.record]
    history = await service.history(
        tenant_id="tenant_public0001", actor_id="usr_patient_test0001", limit=10
    )
    assert "夜间施工噪声" not in history.model_dump_json()


def test_cga_answer_contract_rejects_oversized_supplemental_detail() -> None:
    with pytest.raises(ValidationError):
        CgaAnswerRequest(
            expected_revision=1,
            question_id="psqi_5j",
            score=0,
            supplemental_detail="x" * 501,
        )

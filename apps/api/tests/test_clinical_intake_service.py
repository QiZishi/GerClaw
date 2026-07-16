"""Fail-closed state-machine tests for non-clinical prescription intake."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.database.models import ClinicalIntake
from gerclaw_api.repositories.clinical_intake import ClinicalIntakeNotFoundError
from gerclaw_api.services.clinical_intake_service import (
    ClinicalIntakeConflictError,
    ClinicalIntakeService,
)


class _Repository:
    def __init__(self) -> None:
        self.record: ClinicalIntake | None = None

    async def create(self, **kwargs: object) -> ClinicalIntake:
        self.record = ClinicalIntake(
            id=uuid.uuid4(), status="collecting", revision=1, **kwargs, answers={}
        )
        self.record.updated_at = datetime.now(UTC)
        return self.record

    async def find_by_session_kind(self, **kwargs: object) -> ClinicalIntake | None:
        if (
            self.record is not None
            and self.record.tenant_id == kwargs["tenant_id"]
            and self.record.actor_id == kwargs["actor_id"]
            and self.record.session_id == kwargs["session_id"]
            and self.record.kind == kwargs["kind"]
        ):
            return self.record
        return None

    async def get(self, intake_id: uuid.UUID, **kwargs: str) -> ClinicalIntake:
        if (
            self.record is None
            or self.record.id != intake_id
            or self.record.tenant_id != kwargs["tenant_id"]
            or self.record.actor_id != kwargs["actor_id"]
        ):
            raise ClinicalIntakeNotFoundError(str(intake_id))
        return self.record

    async def lock(self, intake_id: uuid.UUID, **kwargs: str) -> ClinicalIntake:
        return await self.get(intake_id, **kwargs)


class _DocumentService:
    def __init__(self, active_document_ids: set[uuid.UUID]) -> None:
        self.active_document_ids = active_document_ids
        self.calls: list[uuid.UUID] = []

    async def get(self, document_id: uuid.UUID, **_kwargs: object) -> object:
        self.calls.append(document_id)
        if document_id not in self.active_document_ids:
            raise RuntimeError("not found")
        return object()


@pytest.mark.asyncio
async def test_prescription_intake_is_server_defined_and_never_returns_clinical_advice() -> None:
    service = ClinicalIntakeService(_Repository())  # type: ignore[arg-type]
    started = await service.start(
        tenant_id="tenant_public0001",
        actor_id="usr_patient_intake0001",
        session_id=uuid.uuid4(),
        kind="prescription",
    )

    assert started.status == "collecting"
    assert started.missing_required_fields == ["health_goal", "current_concerns"]
    assert "不会生成处方" in started.governance_notice
    assert "剂量" not in started.governance_notice
    assert {field.id for field in started.fields} == {
        "health_goal",
        "current_concerns",
        "current_medications",
    }

    complete = await service.update(
        started.intake_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_intake0001",
        expected_revision=started.revision,
        answers={"health_goal": "希望改善日常活动", "current_concerns": "走路时容易疲劳"},
    )
    assert complete.status == "information_complete_pending_governance"
    assert complete.missing_required_fields == []
    assert complete.revision == 2

    resumed = await service.start(
        tenant_id="tenant_public0001",
        actor_id="usr_patient_intake0001",
        session_id=started.session_id,
        kind="prescription",
    )
    assert resumed.intake_id == started.intake_id
    assert resumed.revision == complete.revision


@pytest.mark.asyncio
async def test_intake_rejects_unknown_or_oversized_fields_and_stale_writes() -> None:
    service = ClinicalIntakeService(_Repository())  # type: ignore[arg-type]
    started = await service.start(
        tenant_id="tenant_public0001",
        actor_id="usr_patient_intake0001",
        session_id=uuid.uuid4(),
        kind="medication_review",
    )

    with pytest.raises(ClinicalIntakeConflictError, match="not declared"):
        await service.update(
            started.intake_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_intake0001",
            expected_revision=started.revision,
            answers={"dose_change": "自行调整"},
        )
    with pytest.raises(ClinicalIntakeConflictError, match="length"):
        await service.update(
            started.intake_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_intake0001",
            expected_revision=started.revision,
            answers={"review_goal": "x" * 501},
        )

    updated = await service.update(
        started.intake_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_intake0001",
        expected_revision=started.revision,
        answers={"review_goal": "担心重复用药"},
    )
    with pytest.raises(ClinicalIntakeConflictError, match="refresh"):
        await service.update(
            started.intake_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_intake0001",
            expected_revision=started.revision,
            answers={"medication_list": "药物名称"},
        )
    replayed = await service.update(
        started.intake_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_intake0001",
        expected_revision=started.revision,
        answers={"review_goal": "担心重复用药"},
    )
    assert replayed.revision == updated.revision


@pytest.mark.asyncio
async def test_intake_hides_missing_records_across_principals() -> None:
    service = ClinicalIntakeService(_Repository())  # type: ignore[arg-type]
    started = await service.start(
        tenant_id="tenant_public0001",
        actor_id="usr_patient_intake0001",
        session_id=uuid.uuid4(),
        kind="prescription",
    )
    with pytest.raises(ClinicalIntakeNotFoundError):
        await service.get(
            started.intake_id,
            tenant_id="tenant_other0001",
            actor_id="usr_patient_other0001",
        )


@pytest.mark.asyncio
async def test_prescription_intake_keeps_owner_scoped_uploaded_documents_as_input_references(
) -> None:
    document_id = uuid.uuid4()
    documents = _DocumentService({document_id})
    service = ClinicalIntakeService(
        _Repository(),  # type: ignore[arg-type]
        documents,  # type: ignore[arg-type]
    )
    started = await service.start(
        tenant_id="tenant_public0001",
        actor_id="usr_patient_intake0001",
        session_id=uuid.uuid4(),
        kind="prescription",
    )

    updated = await service.update(
        started.intake_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_intake0001",
        expected_revision=started.revision,
        answers={},
        document_ids=[document_id],
    )

    assert updated.document_ids == [document_id]
    assert documents.calls == [document_id]
    assert updated.answers == {}
    assert updated.status == "collecting"

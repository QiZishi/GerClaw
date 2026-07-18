"""Owner draft history keeps clinician review results in the same bounded read."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from gerclaw_api.api.routes import clinical_intakes as intake_routes
from gerclaw_api.auth import AuthContext


@pytest.mark.asyncio
async def test_owner_draft_history_projects_all_review_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    patient = "usr_account_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    doctor = "usr_account_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    record = SimpleNamespace(
        id=draft_id,
        clinical_intake_id=intake_id,
        created_at=datetime.now(UTC),
        content={"ignored": "already validated by the production generator"},
    )
    review = SimpleNamespace(
        id=uuid.uuid4(),
        prescription_draft_id=draft_id,
        doctor_actor_id=doctor,
        decision="returned",
        review_note="请补充近期检查结果后再复核。",
        revision=1,
        reviewed_at=datetime.now(UTC),
    )

    class FakeIntakeRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def get(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(kind="prescription")

    class FakeDraftRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def list_for_intake(self, **_kwargs: object) -> list[SimpleNamespace]:
            return [record]

        async def list_reviews_for_drafts(self, **kwargs: object) -> list[SimpleNamespace]:
            assert kwargs["doctor_actor_id"] is None
            return [review]

    async def skip_rate_limit(*_args: object, **_kwargs: object) -> None:
        return None

    class FakeDraftRead:
        def __init__(self, **kwargs: object) -> None:
            self.reviews = kwargs["reviews"]

    class FakeHistory:
        def __init__(self, *, items: tuple[FakeDraftRead, ...]) -> None:
            self.items = items

    class FakeDraft:
        @classmethod
        def model_validate(cls, _value: object) -> SimpleNamespace:
            return SimpleNamespace()

    monkeypatch.setattr(intake_routes, "SqlAlchemyClinicalIntakeRepository", FakeIntakeRepository)
    monkeypatch.setattr(intake_routes, "SqlAlchemyPrescriptionDraftRepository", FakeDraftRepository)
    monkeypatch.setattr(intake_routes, "_enforce_rate_limit", skip_rate_limit)
    monkeypatch.setattr(intake_routes, "FivePrescriptionDraft", FakeDraft)
    monkeypatch.setattr(intake_routes, "PrescriptionDraftRead", FakeDraftRead)
    monkeypatch.setattr(intake_routes, "PrescriptionDraftHistoryRead", FakeHistory)
    result = await intake_routes.list_prescription_drafts(
        intake_id,
        SimpleNamespace(),
        SimpleNamespace(),
        AuthContext(
            actor_id=patient,
            tenant_id="tenant_public0001",
            role="patient",
            account_role="patient",
            scopes=frozenset({"clinical_intake:read"}),
        ),
    )
    assert len(result.items) == 1
    assert result.items[0].reviews[0].doctor_actor_id == doctor
    assert result.items[0].reviews[0].review_note == review.review_note

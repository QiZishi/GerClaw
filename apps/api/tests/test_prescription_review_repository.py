"""Consent-bound clinician review persistence never exposes raw draft storage."""

from __future__ import annotations

import hashlib
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gerclaw_api.repositories.prescription_draft import (
    PrescriptionDraftAmendmentValidationError,
    PrescriptionDraftNotFoundError,
    SqlAlchemyPrescriptionDraftRepository,
)


@pytest.mark.asyncio
async def test_append_review_binds_the_exact_draft_and_increments_per_doctor_revision() -> None:
    draft = SimpleNamespace(
        id=uuid.uuid4(),
        content={"status": "needs_clinician_review", "summary": "private draft"},
    )
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[draft, 2])
    session.add = MagicMock()
    session.flush = AsyncMock()
    repository = SqlAlchemyPrescriptionDraftRepository(session)

    review = await repository.append_review(
        draft_id=draft.id,
        tenant_id="tenant_public0001",
        patient_actor_id="usr_account_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        doctor_actor_id="usr_account_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        decision="returned",
        review_note="请补充近期检查结果后再复核。",
    )

    expected = hashlib.sha256(
        json.dumps(
            draft.content,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert review.prescription_draft_id == draft.id
    assert review.draft_content_sha256 == expected
    assert review.revision == 3
    assert review.review_note == "请补充近期检查结果后再复核。"
    session.add.assert_called_once_with(review)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_append_review_does_not_create_a_record_when_the_patient_draft_is_absent() -> None:
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    session.add = MagicMock()
    repository = SqlAlchemyPrescriptionDraftRepository(session)

    with pytest.raises(PrescriptionDraftNotFoundError):
        await repository.append_review(
            draft_id=uuid.uuid4(),
            tenant_id="tenant_public0001",
            patient_actor_id="usr_account_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            doctor_actor_id="usr_account_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            decision="approved",
            review_note="已核对。",
        )
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_append_review_keeps_clinician_amendment_evidence_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = SimpleNamespace(id=uuid.uuid4(), content={"private": "draft"})
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[draft, 0])
    session.add = MagicMock()
    session.flush = AsyncMock()
    repository = SqlAlchemyPrescriptionDraftRepository(session)

    class ValidDraft:
        evidence_sources = (SimpleNamespace(evidence_id="ev_12345678"),)

    monkeypatch.setattr(
        "gerclaw_api.repositories.prescription_draft.FivePrescriptionDraft.model_validate",
        lambda _content: ValidDraft(),
    )
    review = await repository.append_review(
        draft_id=draft.id,
        tenant_id="tenant_public0001",
        patient_actor_id="usr_account_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        doctor_actor_id="usr_account_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        decision="approved",
        review_note="已结合已有依据完成复核。",
        amended_markdown="## 医生修订\n\n请结合随访结果调整安排。",
        amendment_evidence_ids=("ev_12345678",),
    )

    assert review.amended_markdown is not None
    assert "AI生成建议仅供参考" in review.amended_markdown
    assert review.amendment_evidence_ids == ["ev_12345678"]
    assert (
        review.amended_content_sha256
        == hashlib.sha256(review.amended_markdown.encode()).hexdigest()
    )


@pytest.mark.asyncio
async def test_append_review_rejects_an_amendment_that_cites_an_unknown_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = SimpleNamespace(id=uuid.uuid4(), content={"private": "draft"})
    session = MagicMock()
    session.scalar = AsyncMock(return_value=draft)
    session.add = MagicMock()
    repository = SqlAlchemyPrescriptionDraftRepository(session)

    class ValidDraft:
        evidence_sources = (SimpleNamespace(evidence_id="ev_12345678"),)

    monkeypatch.setattr(
        "gerclaw_api.repositories.prescription_draft.FivePrescriptionDraft.model_validate",
        lambda _content: ValidDraft(),
    )
    with pytest.raises(PrescriptionDraftAmendmentValidationError):
        await repository.append_review(
            draft_id=draft.id,
            tenant_id="tenant_public0001",
            patient_actor_id="usr_account_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            doctor_actor_id="usr_account_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            decision="approved",
            review_note="已完成复核。",
            amended_markdown="## 医生修订",
            amendment_evidence_ids=("ev_unavailable",),
        )
    session.add.assert_not_called()

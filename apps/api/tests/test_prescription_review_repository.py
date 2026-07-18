"""Consent-bound clinician review persistence never exposes raw draft storage."""

from __future__ import annotations

import hashlib
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gerclaw_api.repositories.prescription_draft import (
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

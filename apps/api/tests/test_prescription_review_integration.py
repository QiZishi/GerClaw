"""Real-database doctor review flow for a patient-consented prescription draft."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from gerclaw_api.auth import create_access_token
from gerclaw_api.database.models import PatientAccessGrant, PrescriptionDraftRecord, User
from gerclaw_api.repositories.clinical_intake import SqlAlchemyClinicalIntakeRepository
from gerclaw_api.repositories.conversation import SqlAlchemyConversationRepository
from gerclaw_api.services.conversation_service import ConversationService

pytestmark = pytest.mark.integration

PATIENT = "usr_account_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
DOCTOR = "usr_account_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


@pytest.mark.asyncio
async def test_consented_doctor_review_is_encrypted_and_revision_bound(
    integration_client: tuple[Any, Any],
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    async with app.state.database.session() as session:
        conversation = await ConversationService(
            SqlAlchemyConversationRepository(session)
        ).create_session(session_id, tenant_id="tenant_public0001", actor_id=PATIENT)
        intake = await SqlAlchemyClinicalIntakeRepository(session).create(
            tenant_id="tenant_public0001",
            actor_id=PATIENT,
            session_id=session_id,
            kind="prescription",
            definition_version="clinical-intake-v1",
        )
        draft = PrescriptionDraftRecord(
            tenant_id="tenant_public0001",
            actor_id=PATIENT,
            session_id=session_id,
            clinical_intake_id=intake.id,
            template_version="five-prescription-report-v1",
            workflow_version="1.0.0",
            status="needs_clinician_review",
            content={"private_summary": "sensitive draft content"},
        )
        session.add(draft)
        session.add(
            User(
                tenant_id="tenant_public0001",
                external_id=DOCTOR,
                role="doctor",
                is_active=True,
            )
        )
        session.add(
            PatientAccessGrant(
                tenant_id="tenant_public0001",
                patient_actor_id=PATIENT,
                doctor_actor_id=DOCTOR,
                resource_scope="prescription_draft_review",
                status="active",
                expires_at=datetime.now(UTC) + timedelta(days=1),
                revision=1,
            )
        )
        await session.commit()
        draft_id = draft.id
        assert conversation.user_id is not None

    doctor_token = create_access_token(
        app.state.settings,
        actor_id=DOCTOR,
        tenant_id="tenant_public0001",
        scopes={"clinical_intake:read"},
        role="doctor",
        account_role="doctor",
    )
    review_note = "已核对证据, 建议结合线下检查决定下一步。"
    first = await client.post(
        f"/api/v1/access-grants/patients/{PATIENT}/prescription-drafts/{draft_id}/reviews",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"decision": "returned", "review_note": review_note},
    )
    assert first.status_code == 201
    assert first.json()["decision"] == "returned"
    assert first.json()["revision"] == 1

    second = await client.post(
        f"/api/v1/access-grants/patients/{PATIENT}/prescription-drafts/{draft_id}/reviews",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"decision": "approved", "review_note": "补充信息后已再次核对。"},
    )
    assert second.status_code == 201
    assert second.json()["revision"] == 2

    async with app.state.database.session() as session:
        stored_note = await session.scalar(
            text(
                "SELECT review_note FROM prescription_draft_reviews "
                "WHERE prescription_draft_id = :draft_id ORDER BY revision ASC LIMIT 1"
            ),
            {"draft_id": draft_id},
        )
    assert review_note not in str(stored_note)

"""Real PostgreSQL HITL state, encryption, isolation, and one-time grant tests."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text

from gerclaw_api.auth import create_access_token
from gerclaw_api.database.models import User
from gerclaw_api.modules.runtime.models import (
    ActorRole,
    ApprovalCreate,
    ApprovalDecisionRequest,
    ApprovalStatus,
    RuntimeCheckpoint,
    ToolInvocationRequest,
)
from gerclaw_api.repositories.approval import (
    ApprovalConflictError,
    ApprovalNotFoundError,
    SqlAlchemyApprovalRepository,
)
from gerclaw_api.repositories.checkpoint import (
    CheckpointConflictError,
    CheckpointNotFoundError,
    SqlAlchemyCheckpointRepository,
)
from gerclaw_api.repositories.conversation import SqlAlchemyConversationRepository
from gerclaw_api.services.approval_service import ApprovalService
from gerclaw_api.services.conversation_service import ConversationService

pytestmark = pytest.mark.integration


def approval_command(session_id: uuid.UUID, user_id: uuid.UUID) -> ApprovalCreate:
    return ApprovalCreate(
        user_id=user_id,
        patient_id=user_id,
        session_id=session_id,
        trace_id="trace_approvalintegration01",
        invocation=ToolInvocationRequest(
            invocation_id="invoke_approvalintegration01",
            tool_name="clinical_action",
            tool_version="1.0.0",
            arguments={"private_note": "仅供审批的敏感临床参数"},
            idempotency_key="idem_approvalintegration01",
        ),
        required_roles=(ActorRole.DOCTOR,),
        policy_version="1.0.0",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )


@pytest.mark.asyncio
async def test_approval_is_encrypted_idempotent_atomic_and_one_time(
    integration_client: tuple[Any, Any],
) -> None:
    _, app = integration_client
    session_id = uuid.uuid4()
    async with app.state.database.session() as session:
        conversation = await ConversationService(
            SqlAlchemyConversationRepository(session)
        ).create_session(
            session_id,
            tenant_id="tenant_public0001",
            actor_id="usr_requester_approval01",
        )
        assert conversation.user_id is not None
        doctor = User(
            tenant_id="tenant_public0001",
            external_id="usr_doctor_approval0001",
            role="doctor",
            is_active=True,
        )
        session.add(doctor)
        await session.flush()
        repository = SqlAlchemyApprovalRepository(session)
        command = approval_command(session_id, conversation.user_id)
        created = await repository.create(
            command,
            tenant_id="tenant_public0001",
            requester_actor_id="usr_requester_approval01",
        )
        repeated = await repository.create(
            command,
            tenant_id="tenant_public0001",
            requester_actor_id="usr_requester_approval01",
        )
        assert repeated.id == created.id
        created_id = created.id
        await session.commit()

        raw_arguments = await session.scalar(
            text("SELECT arguments FROM runtime_approvals WHERE id = :id"),
            {"id": created_id},
        )
        assert "敏感临床参数" not in str(raw_arguments)

        service = ApprovalService(repository)
        grant = await service.decide(
            created_id,
            ApprovalDecisionRequest(
                expected_revision=1,
                decision="approved",
                reason="医生已核对患者授权与医学风险",
            ),
            tenant_id="tenant_public0001",
            approver_actor_id="usr_doctor_approval0001",
        )
        assert grant.approval.status is ApprovalStatus.APPROVED
        assert grant.execution_token is not None
        assert "敏感临床参数" not in grant.model_dump_json()
        await session.commit()

        with pytest.raises(ApprovalConflictError):
            await service.decide(
                created_id,
                ApprovalDecisionRequest(
                    expected_revision=1,
                    decision="rejected",
                    reason="重复的过期 revision",
                ),
                tenant_id="tenant_public0001",
                approver_actor_id="usr_doctor_approval0001",
            )
        await session.rollback()

        token_hash = hashlib.sha256(grant.execution_token.encode()).hexdigest()
        consumed = await repository.consume_execution_token(
            created_id,
            tenant_id="tenant_public0001",
            token_hash=token_hash,
        )
        assert consumed.token_consumed_at is not None
        await session.commit()
        with pytest.raises(ApprovalConflictError, match="already consumed"):
            await repository.consume_execution_token(
                created_id,
                tenant_id="tenant_public0001",
                token_hash=token_hash,
            )
        await session.rollback()

        with pytest.raises(ApprovalNotFoundError):
            await repository.get_for_requester(
                created_id,
                tenant_id="tenant_other0001",
                requester_actor_id="usr_requester_approval01",
            )


@pytest.mark.asyncio
async def test_self_approval_and_expired_request_fail_closed(
    integration_client: tuple[Any, Any],
) -> None:
    _, app = integration_client
    session_id = uuid.uuid4()
    async with app.state.database.session() as session:
        conversation = await ConversationService(
            SqlAlchemyConversationRepository(session)
        ).create_session(
            session_id,
            tenant_id="tenant_public0001",
            actor_id="usr_selfapproval_0001",
        )
        assert conversation.user_id is not None
        user = await session.scalar(select(User).where(User.id == conversation.user_id))
        assert user is not None
        user.role = "doctor"
        repository = SqlAlchemyApprovalRepository(session)
        created = await repository.create(
            approval_command(session_id, conversation.user_id),
            tenant_id="tenant_public0001",
            requester_actor_id="usr_selfapproval_0001",
        )
        created_id = created.id
        expires_at = created.expires_at
        await session.commit()
        with pytest.raises(ApprovalConflictError, match="own action"):
            await repository.decide(
                created.id,
                tenant_id="tenant_public0001",
                approver_actor_id="usr_selfapproval_0001",
                approver_role=ActorRole.DOCTOR,
                expected_revision=1,
                decision=ApprovalStatus.APPROVED,
                reason="不允许自批",
                execution_token_hash="a" * 64,
            )
        await session.rollback()

        expired = await repository.decide(
            created_id,
            tenant_id="tenant_public0001",
            approver_actor_id="usr_otherdoctor_0001",
            approver_role=ActorRole.DOCTOR,
            expected_revision=1,
            decision=ApprovalStatus.APPROVED,
            reason="过期审批",
            execution_token_hash="b" * 64,
            now=expires_at + timedelta(seconds=1),
        )
        assert expired.status == ApprovalStatus.EXPIRED.value
        assert expired.execution_token_hash is None
        await session.commit()


@pytest.mark.asyncio
async def test_checkpoint_is_encrypted_version_bound_and_one_time(
    integration_client: tuple[Any, Any],
) -> None:
    _, app = integration_client
    session_id = uuid.uuid4()
    async with app.state.database.session() as session:
        conversation = await ConversationService(
            SqlAlchemyConversationRepository(session)
        ).create_session(
            session_id,
            tenant_id="tenant_public0001",
            actor_id="usr_checkpoint_owner0001",
        )
        assert conversation.user_id is not None
        approval = await SqlAlchemyApprovalRepository(session).create(
            approval_command(session_id, conversation.user_id),
            tenant_id="tenant_public0001",
            requester_actor_id="usr_checkpoint_owner0001",
        )
        checkpoint = RuntimeCheckpoint(
            checkpoint_id=uuid.uuid4(),
            trace_id="trace_approvalintegration01",
            sequence=1,
            schema_version="1.0.0",
            policy_version="1.0.0",
            workflow_version="1.0.0",
            capability_versions={"clinical_action": "1.0.0"},
            completed_steps=("reason",),
            consumed_effect_tokens=(),
            state={"agent_state": "敏感的待恢复上下文"},
            created_at=datetime.now(UTC),
        )
        repository = SqlAlchemyCheckpointRepository(session)
        created = await repository.create(
            checkpoint,
            tenant_id="tenant_public0001",
            actor_id="usr_checkpoint_owner0001",
            user_id=conversation.user_id,
            session_id=session_id,
            approval_id=approval.id,
        )
        repeated = await repository.create(
            checkpoint,
            tenant_id="tenant_public0001",
            actor_id="usr_checkpoint_owner0001",
            user_id=conversation.user_id,
            session_id=session_id,
            approval_id=approval.id,
        )
        assert repeated.id == created.id
        checkpoint_id = created.id
        await session.commit()

        raw_state = await session.scalar(
            text("SELECT state FROM runtime_checkpoints WHERE id = :id"),
            {"id": checkpoint_id},
        )
        assert "敏感的待恢复上下文" not in str(raw_state)

        with pytest.raises(CheckpointNotFoundError):
            await repository.load_parked(
                checkpoint_id,
                tenant_id="tenant_other0001",
                actor_id="usr_checkpoint_owner0001",
                schema_version="1.0.0",
                policy_version="1.0.0",
                workflow_version="1.0.0",
                capability_versions={"clinical_action": "1.0.0"},
            )
        with pytest.raises(CheckpointConflictError, match="incompatible"):
            await repository.load_parked(
                checkpoint_id,
                tenant_id="tenant_public0001",
                actor_id="usr_checkpoint_owner0001",
                schema_version="2.0.0",
                policy_version="1.0.0",
                workflow_version="1.0.0",
                capability_versions={"clinical_action": "1.0.0"},
            )
        await session.rollback()

        resumed = await repository.mark_resumed(
            checkpoint_id,
            tenant_id="tenant_public0001",
            actor_id="usr_checkpoint_owner0001",
            expected_revision=1,
        )
        assert resumed.status == "resumed"
        await session.commit()
        with pytest.raises(CheckpointConflictError, match="terminal"):
            await repository.load_parked(
                checkpoint_id,
                tenant_id="tenant_public0001",
                actor_id="usr_checkpoint_owner0001",
                schema_version="1.0.0",
                policy_version="1.0.0",
                workflow_version="1.0.0",
                capability_versions={"clinical_action": "1.0.0"},
            )


@pytest.mark.asyncio
async def test_approval_api_enforces_scope_owner_and_verified_database_role(
    integration_client: tuple[Any, Any],
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    async with app.state.database.session() as session:
        conversation = await ConversationService(
            SqlAlchemyConversationRepository(session)
        ).create_session(
            session_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_integration0001",
        )
        assert conversation.user_id is not None
        doctor = User(
            tenant_id="tenant_public0001",
            external_id="usr_doctor_apiapproval001",
            role="doctor",
            is_active=True,
        )
        session.add(doctor)
        approval = await SqlAlchemyApprovalRepository(session).create(
            approval_command(session_id, conversation.user_id),
            tenant_id="tenant_public0001",
            requester_actor_id="usr_patient_integration0001",
        )
        approval_id = approval.id
        await session.commit()

    read = await client.get(f"/api/v1/runtime/approvals/{approval_id}")
    assert read.status_code == 200
    assert read.json()["status"] == "pending"
    assert "arguments" not in read.json()

    denied = await client.post(
        f"/api/v1/runtime/approvals/{approval_id}/decision",
        json={"expected_revision": 1, "decision": "approved", "reason": "医生确认"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "AUTH_SCOPE_REQUIRED"

    doctor_token = create_access_token(
        app.state.settings,
        actor_id="usr_doctor_apiapproval001",
        tenant_id="tenant_public0001",
        scopes={"approval:decide"},
    )
    review = await client.get(
        f"/api/v1/runtime/approvals/{approval_id}/review",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert review.status_code == 200
    assert review.json()["arguments"]["private_note"] == "仅供审批的敏感临床参数"
    approved = await client.post(
        f"/api/v1/runtime/approvals/{approval_id}/decision",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"expected_revision": 1, "decision": "approved", "reason": "医生确认"},
    )
    assert approved.status_code == 200
    assert approved.json()["approval"]["status"] == "approved"
    assert len(approved.json()["execution_token"]) >= 32

    cancelled = await client.post(
        f"/api/v1/runtime/approvals/{approval_id}/cancel",
        json={"expected_revision": 1, "reason": "已不需要执行"},
    )
    assert cancelled.status_code == 409
    assert cancelled.json()["error"]["code"] == "APPROVAL_CONFLICT"

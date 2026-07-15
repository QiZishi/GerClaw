"""Approval service never returns a grant unless the repository approved it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gerclaw_api.modules.runtime.models import (
    ActorRole,
    ApprovalCancelRequest,
    ApprovalDecisionRequest,
    ApprovalStatus,
)
from gerclaw_api.services.approval_service import ApprovalService


def _record(status: ApprovalStatus) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        requester_actor_id="usr_requester_service001",
        patient_id=None,
        session_id=uuid.uuid4(),
        trace_id="trace_serviceapproval01",
        invocation_id="invoke_serviceapproval001",
        tool_name="clinical_action",
        tool_version="1.0.0",
        required_roles=[ActorRole.DOCTOR.value],
        policy_version="1.0.0",
        status=status.value,
        revision=2,
        decided_by_actor_id="usr_doctor_service0001",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_approved_service_returns_token_but_expired_does_not() -> None:
    repository = AsyncMock()
    repository.actor_role.return_value = ActorRole.DOCTOR
    repository.decide.return_value = _record(ApprovalStatus.APPROVED)
    service = ApprovalService(repository)
    result = await service.decide(
        uuid.uuid4(),
        ApprovalDecisionRequest(expected_revision=1, decision="approved", reason="医生核对"),
        tenant_id="tenant_public0001",
        approver_actor_id="usr_doctor_service0001",
    )
    assert result.execution_token is not None
    assert repository.decide.await_args.kwargs["execution_token_hash"] is not None

    repository.decide.return_value = _record(ApprovalStatus.EXPIRED)
    expired = await service.decide(
        uuid.uuid4(),
        ApprovalDecisionRequest(expected_revision=1, decision="approved", reason="已经过期"),
        tenant_id="tenant_public0001",
        approver_actor_id="usr_doctor_service0001",
    )
    assert expired.execution_token is None


@pytest.mark.asyncio
async def test_cancel_projects_repository_result() -> None:
    repository = AsyncMock()
    repository.cancel.return_value = _record(ApprovalStatus.CANCELLED)
    result = await ApprovalService(repository).cancel(
        uuid.uuid4(),
        ApprovalCancelRequest(expected_revision=1, reason="用户撤销"),
        tenant_id="tenant_public0001",
        requester_actor_id="usr_requester_service001",
    )
    assert result.status is ApprovalStatus.CANCELLED

"""Fast unit coverage for HITL repository state transitions and fail-closed edges."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gerclaw_api.modules.runtime.models import ActorRole, ApprovalStatus
from gerclaw_api.repositories.approval import (
    ApprovalConflictError,
    ApprovalForbiddenError,
    ApprovalNotFoundError,
    SqlAlchemyApprovalRepository,
)


def _session(record: object | None) -> MagicMock:
    session = MagicMock()
    session.scalar = AsyncMock(return_value=record)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    return session


def _record(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "requester_actor_id": "usr_requester_approval01",
        "revision": 1,
        "status": ApprovalStatus.PENDING.value,
        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
        "required_roles": [ActorRole.DOCTOR.value],
        "execution_token_hash": None,
        "token_consumed_at": None,
        "decision_reason": None,
        "decided_by_actor_id": None,
        "decided_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_get_role_and_commit_are_tenant_safe() -> None:
    found = _record()
    session = _session(found)
    session.scalar = AsyncMock(side_effect=[found, ActorRole.DOCTOR.value])
    repository = SqlAlchemyApprovalRepository(session)
    assert (
        await repository.get_for_requester(
            uuid.uuid4(),
            tenant_id="tenant_public0001",
            requester_actor_id="usr_requester_approval01",
        )
        is found
    )
    assert (
        await repository.actor_role(
            tenant_id="tenant_public0001", actor_id="usr_doctor_approval0001"
        )
        == ActorRole.DOCTOR
    )
    await repository.commit()
    session.commit.assert_awaited_once()

    session.scalar = AsyncMock(return_value=None)
    with pytest.raises(ApprovalNotFoundError):
        await repository.get_for_requester(
            uuid.uuid4(),
            tenant_id="tenant_public0001",
            requester_actor_id="usr_requester_approval01",
        )
    with pytest.raises(ApprovalForbiddenError):
        await repository.actor_role(
            tenant_id="tenant_public0001", actor_id="usr_unknown_approval001"
        )


@pytest.mark.asyncio
async def test_decide_handles_approval_expiry_and_forbidden_edges() -> None:
    record = _record()
    session = _session(record)
    repository = SqlAlchemyApprovalRepository(session)
    decided = await repository.decide(
        uuid.uuid4(),
        tenant_id="tenant_public0001",
        approver_actor_id="usr_doctor_approval0001",
        approver_role=ActorRole.DOCTOR,
        expected_revision=1,
        decision=ApprovalStatus.APPROVED,
        reason="核对完成",
        execution_token_hash="a" * 64,
    )
    assert decided.status == ApprovalStatus.APPROVED.value
    assert decided.revision == 2
    assert decided.execution_token_hash == "a" * 64

    expired = _record(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    session.scalar = AsyncMock(return_value=expired)
    result = await repository.decide(
        uuid.uuid4(),
        tenant_id="tenant_public0001",
        approver_actor_id="usr_doctor_approval0001",
        approver_role=ActorRole.DOCTOR,
        expected_revision=1,
        decision=ApprovalStatus.APPROVED,
        reason="已过期",
        execution_token_hash="b" * 64,
    )
    assert result.status == ApprovalStatus.EXPIRED.value
    assert result.execution_token_hash is None

    with pytest.raises(ApprovalConflictError, match="own action"):
        await repository.decide(
            uuid.uuid4(),
            tenant_id="tenant_public0001",
            approver_actor_id="usr_requester_approval01",
            approver_role=ActorRole.DOCTOR,
            expected_revision=2,
            decision=ApprovalStatus.APPROVED,
            reason="自批",
            execution_token_hash="c" * 64,
        )

    forbidden = _record(required_roles=[ActorRole.ADMIN.value])
    session.scalar = AsyncMock(return_value=forbidden)
    with pytest.raises(ApprovalForbiddenError):
        await repository.decide(
            uuid.uuid4(),
            tenant_id="tenant_public0001",
            approver_actor_id="usr_doctor_approval0001",
            approver_role=ActorRole.DOCTOR,
            expected_revision=1,
            decision=ApprovalStatus.APPROVED,
            reason="角色不符",
            execution_token_hash="d" * 64,
        )


@pytest.mark.asyncio
async def test_cancel_and_consume_are_one_way_and_atomic() -> None:
    record = _record()
    session = _session(record)
    repository = SqlAlchemyApprovalRepository(session)
    cancelled = await repository.cancel(
        uuid.uuid4(),
        tenant_id="tenant_public0001",
        requester_actor_id="usr_requester_approval01",
        expected_revision=1,
        reason="用户撤销",
    )
    assert cancelled.status == ApprovalStatus.CANCELLED.value
    assert cancelled.revision == 2

    executable = _record(
        status=ApprovalStatus.APPROVED.value,
        execution_token_hash="a" * 64,
    )
    session.scalar = AsyncMock(return_value=executable)
    consumed = await repository.consume_execution_token(
        uuid.uuid4(), tenant_id="tenant_public0001", token_hash="a" * 64
    )
    assert consumed.token_consumed_at is not None
    assert consumed.revision == 2

    with pytest.raises(ApprovalConflictError, match="already consumed"):
        await repository.consume_execution_token(
            uuid.uuid4(), tenant_id="tenant_public0001", token_hash="a" * 64
        )

    invalid = _record(status=ApprovalStatus.APPROVED.value, execution_token_hash="b" * 64)
    session.scalar = AsyncMock(return_value=invalid)
    with pytest.raises(ApprovalForbiddenError, match="invalid"):
        await repository.consume_execution_token(
            uuid.uuid4(), tenant_id="tenant_public0001", token_hash="a" * 64
        )

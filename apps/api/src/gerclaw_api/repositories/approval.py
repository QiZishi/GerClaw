"""Atomic tenant-safe persistence for Runtime HITL approvals."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import RuntimeApproval, User
from gerclaw_api.modules.runtime.models import (
    ActorRole,
    ApprovalCreate,
    ApprovalStatus,
)


class ApprovalConflictError(RuntimeError):
    """Idempotency, stale revision, terminal-state, or self-approval conflict."""


class ApprovalNotFoundError(LookupError):
    """Approval is absent or outside the caller's tenant/ownership boundary."""


class ApprovalForbiddenError(PermissionError):
    """Verified actor role cannot decide the approval."""


def _fingerprint(command: ApprovalCreate) -> str:
    canonical = json.dumps(
        command.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class SqlAlchemyApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        """Durably park a HITL request before an Agent turn is ended."""

        await self._session.commit()

    async def create(
        self,
        command: ApprovalCreate,
        *,
        tenant_id: str,
        requester_actor_id: str,
    ) -> RuntimeApproval:
        if command.invocation.idempotency_key is None:
            raise ValueError("approval requires a tool idempotency key")
        fingerprint = _fingerprint(command)
        existing = await self._session.scalar(
            select(RuntimeApproval).where(
                RuntimeApproval.tenant_id == tenant_id,
                RuntimeApproval.idempotency_key == command.invocation.idempotency_key,
            )
        )
        if existing is not None:
            if existing.argument_fingerprint != fingerprint:
                raise ApprovalConflictError("approval idempotency key payload differs")
            return existing
        record = RuntimeApproval(
            tenant_id=tenant_id,
            requester_actor_id=requester_actor_id,
            user_id=command.user_id,
            patient_id=command.patient_id,
            session_id=command.session_id,
            trace_id=command.trace_id,
            invocation_id=command.invocation.invocation_id,
            tool_name=command.invocation.tool_name,
            tool_version=command.invocation.tool_version,
            arguments=command.invocation.arguments,
            argument_fingerprint=fingerprint,
            idempotency_key=command.invocation.idempotency_key,
            required_roles=[item.value for item in command.required_roles],
            policy_version=command.policy_version,
            expires_at=command.expires_at,
        )
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise ApprovalConflictError(
                "approval invocation or idempotency key conflicts"
            ) from error
        return record

    async def get_for_requester(
        self,
        approval_id: uuid.UUID,
        *,
        tenant_id: str,
        requester_actor_id: str,
    ) -> RuntimeApproval:
        record = await self._session.scalar(
            select(RuntimeApproval).where(
                RuntimeApproval.id == approval_id,
                RuntimeApproval.tenant_id == tenant_id,
                RuntimeApproval.requester_actor_id == requester_actor_id,
            )
        )
        if record is None:
            raise ApprovalNotFoundError("approval not found")
        return record

    async def actor_role(self, *, tenant_id: str, actor_id: str) -> ActorRole:
        role = await self._session.scalar(
            select(User.role).where(
                User.tenant_id == tenant_id,
                User.external_id == actor_id,
                User.is_active.is_(True),
            )
        )
        if role is None:
            raise ApprovalForbiddenError("approver identity has no active user role")
        return ActorRole(role)

    async def get_for_approver(
        self,
        approval_id: uuid.UUID,
        *,
        tenant_id: str,
        approver_actor_id: str,
    ) -> RuntimeApproval:
        """Decrypt review details only after verified active-role authorization."""

        role = await self.actor_role(tenant_id=tenant_id, actor_id=approver_actor_id)
        record = await self._session.scalar(
            select(RuntimeApproval).where(
                RuntimeApproval.id == approval_id,
                RuntimeApproval.tenant_id == tenant_id,
            )
        )
        if record is None:
            raise ApprovalNotFoundError("approval not found")
        if record.requester_actor_id == approver_actor_id:
            raise ApprovalConflictError("requester cannot review their own action")
        if role.value not in record.required_roles:
            raise ApprovalForbiddenError("approver role is not permitted")
        return record

    async def cancel(
        self,
        approval_id: uuid.UUID,
        *,
        tenant_id: str,
        requester_actor_id: str,
        expected_revision: int,
        reason: str,
        now: datetime | None = None,
    ) -> RuntimeApproval:
        record = await self._session.scalar(
            select(RuntimeApproval)
            .where(
                RuntimeApproval.id == approval_id,
                RuntimeApproval.tenant_id == tenant_id,
                RuntimeApproval.requester_actor_id == requester_actor_id,
            )
            .with_for_update()
        )
        if record is None:
            raise ApprovalNotFoundError("approval not found")
        if record.revision != expected_revision or record.status != ApprovalStatus.PENDING.value:
            raise ApprovalConflictError("approval revision is stale or already terminal")
        record.status = ApprovalStatus.CANCELLED.value
        record.decision_reason = reason
        record.decided_by_actor_id = requester_actor_id
        record.decided_at = now or datetime.now(UTC)
        record.revision += 1
        await self._session.flush()
        await self._session.refresh(record)
        return record

    async def decide(
        self,
        approval_id: uuid.UUID,
        *,
        tenant_id: str,
        approver_actor_id: str,
        approver_role: ActorRole,
        expected_revision: int,
        decision: ApprovalStatus,
        reason: str,
        execution_token_hash: str | None,
        now: datetime | None = None,
    ) -> RuntimeApproval:
        current_time = now or datetime.now(UTC)
        record = await self._session.scalar(
            select(RuntimeApproval)
            .where(
                RuntimeApproval.id == approval_id,
                RuntimeApproval.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if record is None:
            raise ApprovalNotFoundError("approval not found")
        if record.requester_actor_id == approver_actor_id:
            raise ApprovalConflictError("requester cannot approve their own action")
        if record.revision != expected_revision or record.status != ApprovalStatus.PENDING.value:
            raise ApprovalConflictError("approval revision is stale or already terminal")
        if record.expires_at <= current_time:
            record.status = ApprovalStatus.EXPIRED.value
            record.revision += 1
            await self._session.flush()
            await self._session.refresh(record)
            return record
        if approver_role.value not in record.required_roles:
            raise ApprovalForbiddenError("approver role is not permitted")
        if decision not in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise ValueError("decision must be approved or rejected")
        if decision is ApprovalStatus.APPROVED and execution_token_hash is None:
            raise ValueError("approved decision requires an execution token")
        if decision is ApprovalStatus.REJECTED and execution_token_hash is not None:
            raise ValueError("rejected decision cannot receive an execution token")
        record.status = decision.value
        record.decision_reason = reason
        record.decided_by_actor_id = approver_actor_id
        record.decided_at = current_time
        record.execution_token_hash = execution_token_hash
        record.revision += 1
        await self._session.flush()
        await self._session.refresh(record)
        return record

    async def consume_execution_token(
        self,
        approval_id: uuid.UUID,
        *,
        tenant_id: str,
        token_hash: str,
        now: datetime | None = None,
    ) -> RuntimeApproval:
        record = await self._session.scalar(
            select(RuntimeApproval)
            .where(
                RuntimeApproval.id == approval_id,
                RuntimeApproval.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if record is None:
            raise ApprovalNotFoundError("approval not found")
        if record.status != ApprovalStatus.APPROVED.value or record.execution_token_hash is None:
            raise ApprovalConflictError("approval has no executable grant")
        if not hmac.compare_digest(record.execution_token_hash, token_hash):
            raise ApprovalForbiddenError("execution token is invalid")
        if record.token_consumed_at is not None:
            raise ApprovalConflictError("execution token was already consumed")
        record.token_consumed_at = now or datetime.now(UTC)
        record.revision += 1
        await self._session.flush()
        await self._session.refresh(record)
        return record

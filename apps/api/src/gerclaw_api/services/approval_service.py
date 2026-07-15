"""HITL approval orchestration with one-time opaque execution grants."""

from __future__ import annotations

import hashlib
import secrets
import uuid

from gerclaw_api.modules.runtime.models import (
    ApprovalCancelRequest,
    ApprovalDecisionRequest,
    ApprovalGrant,
    ApprovalRead,
    ApprovalStatus,
)
from gerclaw_api.repositories.approval import SqlAlchemyApprovalRepository


class ApprovalService:
    def __init__(self, repository: SqlAlchemyApprovalRepository) -> None:
        self._repository = repository

    async def decide(
        self,
        approval_id: uuid.UUID,
        payload: ApprovalDecisionRequest,
        *,
        tenant_id: str,
        approver_actor_id: str,
    ) -> ApprovalGrant:
        role = await self._repository.actor_role(tenant_id=tenant_id, actor_id=approver_actor_id)
        raw_token = secrets.token_urlsafe(48) if payload.decision == "approved" else None
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest() if raw_token else None
        record = await self._repository.decide(
            approval_id,
            tenant_id=tenant_id,
            approver_actor_id=approver_actor_id,
            approver_role=role,
            expected_revision=payload.expected_revision,
            decision=ApprovalStatus(payload.decision),
            reason=payload.reason,
            execution_token_hash=token_hash,
        )
        return ApprovalGrant(
            approval=ApprovalRead.model_validate(record),
            execution_token=(raw_token if record.status == ApprovalStatus.APPROVED.value else None),
        )

    async def cancel(
        self,
        approval_id: uuid.UUID,
        payload: ApprovalCancelRequest,
        *,
        tenant_id: str,
        requester_actor_id: str,
    ) -> ApprovalRead:
        record = await self._repository.cancel(
            approval_id,
            tenant_id=tenant_id,
            requester_actor_id=requester_actor_id,
            expected_revision=payload.expected_revision,
            reason=payload.reason,
        )
        return ApprovalRead.model_validate(record)

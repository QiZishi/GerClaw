"""Tenant-scoped Runtime HITL status, decision, and cancellation endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import (
    AuthContext,
    require_approval_decide,
    require_approval_read,
    require_approval_write,
)
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.modules.runtime.models import (
    ApprovalCancelRequest,
    ApprovalDecisionRequest,
    ApprovalGrant,
    ApprovalRead,
    ApprovalReviewRead,
)
from gerclaw_api.repositories.approval import SqlAlchemyApprovalRepository
from gerclaw_api.services.approval_service import ApprovalService

router = APIRouter(prefix="/runtime/approvals", tags=["runtime"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
ReadIdentity = Annotated[AuthContext, Depends(require_approval_read)]
WriteIdentity = Annotated[AuthContext, Depends(require_approval_write)]
DecideIdentity = Annotated[AuthContext, Depends(require_approval_decide)]


@router.get("/{approval_id}", response_model=ApprovalRead)
async def get_approval(
    approval_id: uuid.UUID,
    session: SessionDependency,
    identity: ReadIdentity,
) -> ApprovalRead:
    """Read only a request created by the authenticated actor."""

    record = await SqlAlchemyApprovalRepository(session).get_for_requester(
        approval_id,
        tenant_id=identity.tenant_id,
        requester_actor_id=identity.actor_id,
    )
    return ApprovalRead.model_validate(record)


@router.post("/{approval_id}/decision", response_model=ApprovalGrant)
async def decide_approval(
    approval_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    session: SessionDependency,
    identity: DecideIdentity,
) -> ApprovalGrant:
    """Atomically decide with both verified scope and active database role."""

    service = ApprovalService(SqlAlchemyApprovalRepository(session))
    result = await service.decide(
        approval_id,
        payload,
        tenant_id=identity.tenant_id,
        approver_actor_id=identity.actor_id,
    )
    await session.commit()
    return result


@router.get("/{approval_id}/review", response_model=ApprovalReviewRead)
async def review_approval(
    approval_id: uuid.UUID,
    session: SessionDependency,
    identity: DecideIdentity,
) -> ApprovalReviewRead:
    """Return decrypted action arguments solely to the verified required approver."""

    record = await SqlAlchemyApprovalRepository(session).get_for_approver(
        approval_id,
        tenant_id=identity.tenant_id,
        approver_actor_id=identity.actor_id,
    )
    return ApprovalReviewRead(
        approval=ApprovalRead.model_validate(record),
        arguments=record.arguments,
    )


@router.post("/{approval_id}/cancel", response_model=ApprovalRead)
async def cancel_approval(
    approval_id: uuid.UUID,
    payload: ApprovalCancelRequest,
    session: SessionDependency,
    identity: WriteIdentity,
) -> ApprovalRead:
    """Cancel only the authenticated requester's still-pending request."""

    service = ApprovalService(SqlAlchemyApprovalRepository(session))
    result = await service.cancel(
        approval_id,
        payload,
        tenant_id=identity.tenant_id,
        requester_actor_id=identity.actor_id,
    )
    await session.commit()
    return result

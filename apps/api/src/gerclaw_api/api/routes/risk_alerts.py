"""Caller-owned deterministic risk alert read and acknowledgement endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import AuthContext, require_risk_alert_read, require_risk_alert_write
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.modules.risk_alert.models import (
    RiskAlertAcknowledgeRequest,
    RiskAlertListRead,
    RiskAlertRead,
)
from gerclaw_api.modules.risk_alert.service import RiskAlertConflictError, RiskAlertService
from gerclaw_api.repositories.risk_alert import (
    RiskAlertNotFoundError,
    SqlAlchemyRiskAlertRepository,
)

router = APIRouter(prefix="/risk-alerts", tags=["risk-alerts"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
ReadIdentity = Annotated[AuthContext, Depends(require_risk_alert_read)]
WriteIdentity = Annotated[AuthContext, Depends(require_risk_alert_write)]


@router.get("", response_model=RiskAlertListRead)
async def list_risk_alerts(
    session: SessionDependency,
    identity: ReadIdentity,
    status: Annotated[Literal["active", "acknowledged"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> RiskAlertListRead:
    """Return only a bounded projection of the authenticated owner's alerts."""

    return await RiskAlertService(SqlAlchemyRiskAlertRepository(session)).list(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        status=status,
        limit=limit,
    )


@router.post("/{alert_id}/acknowledgements", response_model=RiskAlertRead)
async def acknowledge_risk_alert(
    alert_id: uuid.UUID,
    payload: RiskAlertAcknowledgeRequest,
    session: SessionDependency,
    identity: WriteIdentity,
) -> RiskAlertRead:
    """Record an explicit, revision-fenced acknowledgement without dismissing risk."""

    try:
        result = await RiskAlertService(SqlAlchemyRiskAlertRepository(session)).acknowledge(
            alert_id=alert_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            expected_revision=payload.expected_revision,
            idempotency_key=payload.idempotency_key,
        )
    except RiskAlertNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "RISK_ALERT_NOT_FOUND"}) from error
    except RiskAlertConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "RISK_ALERT_CONFLICT"}) from error
    await session.commit()
    return result

"""Tenant- and actor-scoped persistence for deterministic risk alerts."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import RiskAlert


class RiskAlertNotFoundError(RuntimeError):
    """The requested alert is absent or belongs to another caller."""


class SqlAlchemyRiskAlertRepository:
    """Every lookup applies the verified tenant and actor boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_source(
        self, *, tenant_id: str, actor_id: str, source_fingerprint: str
    ) -> RiskAlert | None:
        statement = select(RiskAlert).where(
            RiskAlert.tenant_id == tenant_id,
            RiskAlert.actor_id == actor_id,
            RiskAlert.source_fingerprint == source_fingerprint,
        )
        return cast(RiskAlert | None, await self._session.scalar(statement))

    async def create(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        source: str,
        source_fingerprint: str,
        policy_version: str,
        details: dict[str, object],
    ) -> RiskAlert:
        statement = (
            insert(RiskAlert)
            .values(
                tenant_id=tenant_id,
                actor_id=actor_id,
                source=source,
                source_fingerprint=source_fingerprint,
                policy_version=policy_version,
                details=details,
                status="active",
                revision=1,
            )
            .on_conflict_do_nothing(constraint="uq_risk_alerts_owner_source")
            .returning(RiskAlert)
        )
        record = cast(RiskAlert | None, await self._session.scalar(statement))
        if record is not None:
            return record
        existing = await self.get_by_source(
            tenant_id=tenant_id, actor_id=actor_id, source_fingerprint=source_fingerprint
        )
        if existing is None:  # pragma: no cover - database isolation failure
            raise RuntimeError("risk alert insertion did not return a record")
        return existing

    async def list_for_owner(
        self, *, tenant_id: str, actor_id: str, status: str | None, limit: int
    ) -> list[RiskAlert]:
        statement = select(RiskAlert).where(
            RiskAlert.tenant_id == tenant_id,
            RiskAlert.actor_id == actor_id,
        )
        if status is not None:
            statement = statement.where(RiskAlert.status == status)
        statement = statement.order_by(RiskAlert.updated_at.desc(), RiskAlert.id.desc()).limit(
            limit
        )
        return list((await self._session.scalars(statement)).all())

    async def lock(self, *, alert_id: uuid.UUID, tenant_id: str, actor_id: str) -> RiskAlert:
        statement = (
            select(RiskAlert)
            .where(
                RiskAlert.id == alert_id,
                RiskAlert.tenant_id == tenant_id,
                RiskAlert.actor_id == actor_id,
            )
            .with_for_update()
        )
        record = cast(RiskAlert | None, await self._session.scalar(statement))
        if record is None:
            raise RiskAlertNotFoundError(str(alert_id))
        return record

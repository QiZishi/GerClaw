"""Tenant- and actor-scoped persistence for encrypted chronic-care ledger records."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import ChronicCareCondition, ChronicCareMeasurement


class ChronicCareNotFoundError(RuntimeError):
    """The caller cannot observe the requested condition or measurement."""


class SqlAlchemyChronicCareRepository:
    """Every operation binds conditions and measurements to tenant plus actor."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_condition(
        self, *, tenant_id: str, actor_id: str, details: dict[str, object]
    ) -> ChronicCareCondition:
        record = ChronicCareCondition(
            tenant_id=tenant_id,
            actor_id=actor_id,
            confirmation_status="self_reported",
            revision=1,
            details=details,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_conditions(
        self, *, tenant_id: str, actor_id: str, limit: int
    ) -> list[ChronicCareCondition]:
        statement = (
            select(ChronicCareCondition)
            .where(
                ChronicCareCondition.tenant_id == tenant_id,
                ChronicCareCondition.actor_id == actor_id,
            )
            .order_by(ChronicCareCondition.updated_at.desc(), ChronicCareCondition.id.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_condition(
        self, condition_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ChronicCareCondition:
        statement = select(ChronicCareCondition).where(
            ChronicCareCondition.id == condition_id,
            ChronicCareCondition.tenant_id == tenant_id,
            ChronicCareCondition.actor_id == actor_id,
        )
        record = cast(ChronicCareCondition | None, await self._session.scalar(statement))
        if record is None:
            raise ChronicCareNotFoundError(str(condition_id))
        return record

    async def create_measurement(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        condition_id: uuid.UUID,
        details: dict[str, object],
    ) -> ChronicCareMeasurement:
        await self.get_condition(condition_id, tenant_id=tenant_id, actor_id=actor_id)
        record = ChronicCareMeasurement(
            tenant_id=tenant_id,
            actor_id=actor_id,
            condition_id=condition_id,
            details=details,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_measurements(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        condition_id: uuid.UUID,
        limit: int,
    ) -> list[ChronicCareMeasurement]:
        await self.get_condition(condition_id, tenant_id=tenant_id, actor_id=actor_id)
        statement = (
            select(ChronicCareMeasurement)
            .where(
                ChronicCareMeasurement.tenant_id == tenant_id,
                ChronicCareMeasurement.actor_id == actor_id,
                ChronicCareMeasurement.condition_id == condition_id,
            )
            .order_by(ChronicCareMeasurement.created_at.desc(), ChronicCareMeasurement.id.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

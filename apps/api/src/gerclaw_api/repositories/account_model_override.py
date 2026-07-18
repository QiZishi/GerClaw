"""Tenant-safe encrypted persistence for account model configuration."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import AccountModelOverride


class AccountModelOverrideConflictError(RuntimeError):
    """The caller attempted to overwrite a newer configuration revision."""


class SqlAlchemyAccountModelOverrideRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, tenant_id: str, actor_id: str) -> AccountModelOverride | None:
        record = await self._session.scalar(
            select(AccountModelOverride).where(
                AccountModelOverride.tenant_id == tenant_id,
                AccountModelOverride.actor_id == actor_id,
            )
        )
        return record

    async def replace(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        configuration: dict[str, Any],
        expected_revision: int,
    ) -> AccountModelOverride:
        record = await self._session.scalar(
            select(AccountModelOverride)
            .where(
                AccountModelOverride.tenant_id == tenant_id,
                AccountModelOverride.actor_id == actor_id,
            )
            .with_for_update()
        )
        if record is None:
            if expected_revision != 0:
                raise AccountModelOverrideConflictError("configuration revision is stale")
            record = AccountModelOverride(
                tenant_id=tenant_id,
                actor_id=actor_id,
                configuration=configuration,
                revision=1,
            )
            self._session.add(record)
        else:
            if record.revision != expected_revision:
                raise AccountModelOverrideConflictError("configuration revision is stale")
            record.configuration = configuration
            record.revision += 1
        await self._session.flush()
        await self._session.refresh(record)
        return record

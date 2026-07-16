"""Persistence for local credentials and opaque refresh sessions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import AccountCredential, AccountRefreshSession, User


class AccountConflictError(RuntimeError):
    """A local account name is already unavailable."""


class AccountNotFoundError(RuntimeError):
    """Credentials do not identify an active local account."""


class SqlAlchemyAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        role: Literal["patient", "doctor"],
        username_fingerprint: str,
        username: str,
        password_hash: str,
    ) -> User:
        user = User(
            tenant_id=tenant_id,
            external_id=actor_id,
            role=role,
            is_active=True,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(user)
                await self._session.flush()
                self._session.add(
                    AccountCredential(
                        tenant_id=tenant_id,
                        user_id=user.id,
                        username_fingerprint=username_fingerprint,
                        username=username,
                        password_hash=password_hash,
                        password_version=1,
                    )
                )
                await self._session.flush()
        except IntegrityError as error:
            raise AccountConflictError("account name is unavailable") from error
        return user

    async def find_by_username(
        self, *, tenant_id: str, username_fingerprint: str
    ) -> tuple[User, AccountCredential]:
        statement = (
            select(User, AccountCredential)
            .join(AccountCredential, AccountCredential.user_id == User.id)
            .where(
                User.tenant_id == tenant_id,
                User.is_active.is_(True),
                AccountCredential.tenant_id == tenant_id,
                AccountCredential.username_fingerprint == username_fingerprint,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            raise AccountNotFoundError("account is unavailable")
        return cast(User, row[0]), cast(AccountCredential, row[1])

    async def create_refresh_session(
        self, *, tenant_id: str, user_id: uuid.UUID, token_fingerprint: str, expires_at: datetime
    ) -> AccountRefreshSession:
        record = AccountRefreshSession(
            tenant_id=tenant_id,
            user_id=user_id,
            token_fingerprint=token_fingerprint,
            token_version=1,
            expires_at=expires_at,
        )
        self._session.add(record)
        await self._session.flush()
        return record

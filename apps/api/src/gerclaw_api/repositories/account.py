"""Persistence for local credentials and opaque refresh sessions."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import (
    AccountCredential,
    AccountRefreshSession,
    IdentitySecurityEvent,
    User,
)

_AUDIT_FINGERPRINT = re.compile(r"^[a-z2-7]{52}$")


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
        role: Literal["patient", "doctor", "admin"],
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

    async def list_accounts(
        self, *, tenant_id: str, limit: int, after_actor_id: str | None
    ) -> list[tuple[User, AccountCredential]]:
        statement = (
            select(User, AccountCredential)
            .join(AccountCredential, AccountCredential.user_id == User.id)
            .where(User.tenant_id == tenant_id, AccountCredential.tenant_id == tenant_id)
            .order_by(User.external_id.asc())
            .limit(limit)
        )
        if after_actor_id is not None:
            statement = statement.where(User.external_id > after_actor_id)
        return [
            (cast(User, row[0]), cast(AccountCredential, row[1]))
            for row in (await self._session.execute(statement)).all()
        ]

    async def lock_account_by_actor(
        self, *, tenant_id: str, actor_id: str
    ) -> tuple[User, AccountCredential]:
        statement = (
            select(User, AccountCredential)
            .join(AccountCredential, AccountCredential.user_id == User.id)
            .where(
                User.tenant_id == tenant_id,
                User.external_id == actor_id,
                AccountCredential.tenant_id == tenant_id,
            )
            .with_for_update()
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

    async def lock_refresh_session(
        self, *, token_fingerprint: str
    ) -> tuple[AccountRefreshSession, User]:
        statement = (
            select(AccountRefreshSession, User)
            .join(User, User.id == AccountRefreshSession.user_id)
            .where(
                AccountRefreshSession.token_fingerprint == token_fingerprint,
                AccountRefreshSession.revoked_at.is_(None),
                AccountRefreshSession.expires_at > datetime.now(UTC),
                User.is_active.is_(True),
            )
            .with_for_update()
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            raise AccountNotFoundError("refresh session is unavailable")
        return cast(AccountRefreshSession, row[0]), cast(User, row[1])

    async def revoke_refresh_session(self, record: AccountRefreshSession) -> None:
        record.revoked_at = datetime.now(UTC)

    async def lock_credential_by_actor(
        self, *, tenant_id: str, actor_id: str
    ) -> tuple[User, AccountCredential]:
        statement = (
            select(User, AccountCredential)
            .join(AccountCredential, AccountCredential.user_id == User.id)
            .where(
                User.tenant_id == tenant_id,
                User.external_id == actor_id,
                User.is_active.is_(True),
                AccountCredential.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            raise AccountNotFoundError("account is unavailable")
        return cast(User, row[0]), cast(AccountCredential, row[1])

    async def revoke_all_refresh_sessions(self, *, user_id: uuid.UUID) -> None:
        await self._session.execute(
            update(AccountRefreshSession)
            .where(
                AccountRefreshSession.user_id == user_id,
                AccountRefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )

    async def deactivate_user(self, user: User) -> None:
        """Disable a locally authenticated account after its sessions are revoked."""

        user.is_active = False

    async def record_security_event(
        self,
        *,
        tenant_id: str,
        subject_fingerprint: str,
        event_type: Literal[
            "register", "login", "refresh", "logout", "password_change", "deactivate",
            "admin_update", "bootstrap",
        ],
        outcome: Literal["succeeded", "rejected", "ignored"],
        actor_id: str | None = None,
        role: Literal["patient", "doctor", "admin"] | None = None,
    ) -> None:
        """Stage a bounded audit fact; callers commit it with the auth operation."""

        if _AUDIT_FINGERPRINT.fullmatch(subject_fingerprint) is None:
            raise ValueError("identity audit subject must be a keyed opaque fingerprint")
        self._session.add(
            IdentitySecurityEvent(
                tenant_id=tenant_id,
                actor_id=actor_id,
                subject_fingerprint=subject_fingerprint,
                event_type=event_type,
                outcome=outcome,
                role=role,
            )
        )

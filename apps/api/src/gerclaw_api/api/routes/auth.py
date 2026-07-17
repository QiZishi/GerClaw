"""Authenticated local accounts, administrative account operations and sessions."""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from gerclaw_api.auth import (
    AuthContext,
    account_access_revocation_key,
    authenticate,
    create_access_token,
    require_account_admin,
)
from gerclaw_api.database.models import BadCase
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.modules.identity.passwords import hash_password, verify_password
from gerclaw_api.repositories.account import (
    AccountConflictError,
    AccountNotFoundError,
    SqlAlchemyAccountRepository,
)
from gerclaw_api.security import audit_hmac_digest
from gerclaw_api.services.rate_limit import RateLimiter

router = APIRouter(prefix="/auth", tags=["auth"])

_ACCOUNT_SCOPES = {
    "approval:read",
    "approval:write",
    "chat:read",
    "chat:write",
    "document:read",
    "document:write",
    "cga:read",
    "cga:write",
    "chronic_care:read",
    "chronic_care:write",
    "clinical_intake:read",
    "clinical_intake:write",
    "feedback:write",
    "memory:read",
    "memory:write",
    "rag:read",
    "risk_alert:read",
    "risk_alert:write",
    "search:read",
    "skill:execute",
    "skill:read",
    "skill:write",
    "trace:read",
    "trace:write",
    "voice:use",
}
_VISITOR_ID = re.compile(r"^[a-f0-9]{32}$")
_VISITOR_SIGNATURE = re.compile(r"^[a-f0-9]{64}$")
_ACCOUNT_NAME = r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,47}$"
_ACCOUNT_TENANT = "tenant_public0001"
AccountSessionDependency = Annotated[AsyncSession, Depends(get_database_session)]


class GuestTokenRead(BaseModel):
    """Ephemeral patient-only visitor credential, issued only to the BFF."""

    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(min_length=32)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(ge=300, le=86_400)
    actor_id: str = Field(pattern=r"^usr_guest_[a-f0-9]{32}$")


class AccountRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(pattern=_ACCOUNT_NAME)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["patient", "doctor"]


class AccountLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(pattern=_ACCOUNT_NAME)
    password: str = Field(min_length=1, max_length=128)


class AccountRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=32, max_length=256)


class AccountPasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class AccountDeactivationRequest(BaseModel):
    """Explicit password confirmation for an irreversible sign-in disablement."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)


class AccountSessionRead(BaseModel):
    """Tokens are returned to the same-origin BFF, never persisted by the API."""

    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(min_length=32)
    refresh_token: str = Field(min_length=32)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(ge=300, le=86_400)
    actor_id: str = Field(pattern=r"^usr_account_[a-f0-9]{32}$")
    role: Literal["patient", "doctor", "admin"]
    account_role: Literal["patient", "doctor", "admin"]


class AccountIdentityRead(BaseModel):
    """Verified current account identity, intentionally without credentials."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str = Field(pattern=r"^usr_account_[a-f0-9]{32}$")
    role: Literal["patient", "doctor", "admin"]
    account_role: Literal["patient", "doctor", "admin"]


class AccountAdminRead(BaseModel):
    """Identity data exposed only to an authenticated administrator."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str = Field(pattern=r"^usr_account_[a-f0-9]{32}$")
    username: str = Field(min_length=3, max_length=48)
    role: Literal["patient", "doctor", "admin"]
    is_active: bool
    created_at: datetime


class AccountAdminListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accounts: list[AccountAdminRead]
    next_after_actor_id: str | None = None


class AccountAdminUpdateRequest(BaseModel):
    """Administrators may manage application accounts but cannot mint administrators."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["patient", "doctor"] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def has_change(self) -> AccountAdminUpdateRequest:
        if self.role is None and self.is_active is None:
            raise ValueError("one account change is required")
        return self


class BadCaseAdminRead(BaseModel):
    """PHI-free review metadata; encrypted snapshots are never exposed here."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    trace_id: str
    source: Literal["execution_failure", "negative_feedback"]
    reason_codes: list[str]
    severity: Literal["low", "medium", "high", "critical"]
    status: Literal["open", "triaged", "resolved", "dismissed"]
    created_at: datetime
    resolved_at: datetime | None


class BadCaseAdminListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cases: list[BadCaseAdminRead]


class BadCaseAdminUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "triaged", "resolved", "dismissed"]


class AccountViewRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["patient", "doctor"]


def _account_scopes(account_role: Literal["patient", "doctor", "admin"]) -> set[str]:
    """Account role is not a substitute for patient or clinical authorisation."""

    scopes = set(_ACCOUNT_SCOPES)
    if account_role == "admin":
        scopes.add("account:admin")
    return scopes


def _guest_scopes() -> set[str]:
    """Visitors receive the patient-service subset, never doctor/admin authority."""

    return set(_ACCOUNT_SCOPES) - {
        "approval:write",
        "skill:read",
        "skill:write",
        "skill:execute",
    }


@router.get("/session", response_model=AccountIdentityRead)
async def read_account_session(
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> AccountIdentityRead:
    """Return only the verified account role needed to render the authenticated UI."""

    is_account = identity.actor_id.startswith("usr_account_")
    if identity.account_role not in {"patient", "doctor", "admin"} or not is_account:
        raise HTTPException(status_code=403, detail={"code": "ACCOUNT_REQUIRED"})
    return AccountIdentityRead(
        actor_id=identity.actor_id,
        role=identity.role,
        account_role=identity.account_role,
    )


def _username_fingerprint(request: Request, username: str) -> str:
    normalized = username.strip().casefold()
    return audit_hmac_digest(
        request.app.state.settings.auth_jwt_secret.get_secret_value().encode(),
        f"local-account-name:v1:{normalized}".encode(),
    )


def _opaque_subject_fingerprint(request: Request, *, namespace: str, value: str) -> str:
    """Correlate a security event without retaining a credential or identifier."""

    return audit_hmac_digest(
        request.app.state.settings.auth_jwt_secret.get_secret_value().encode(),
        f"local-account-audit:v1:{namespace}:{value}".encode(),
    )


async def _issue_account_session(
    request: Request,
    repository: SqlAlchemyAccountRepository,
    *,
    user_id: uuid.UUID,
    actor_id: str,
    account_role: Literal["patient", "doctor", "admin"],
    active_role: Literal["patient", "doctor", "admin"] | None = None,
) -> AccountSessionRead:
    settings = request.app.state.settings
    refresh_token = uuid.uuid4().hex + uuid.uuid4().hex
    await repository.create_refresh_session(
        tenant_id=_ACCOUNT_TENANT,
        user_id=user_id,
        token_fingerprint=audit_hmac_digest(
            settings.auth_jwt_secret.get_secret_value().encode(),
            f"local-account-refresh:v1:{refresh_token}".encode(),
        ),
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    return AccountSessionRead(
        access_token=create_access_token(
            settings,
            actor_id=actor_id,
            tenant_id=_ACCOUNT_TENANT,
            scopes=_account_scopes(account_role),
            role=active_role or account_role,
            account_role=account_role,
            lifetime_seconds=900,
        ),
        refresh_token=refresh_token,
        expires_in=900,
        actor_id=actor_id,
        role=active_role or account_role,
        account_role=account_role,
    )


@router.post("/register", response_model=AccountSessionRead, status_code=status.HTTP_201_CREATED)
async def register_account(
    payload: AccountRegisterRequest,
    request: Request,
    session: AccountSessionDependency,
) -> AccountSessionRead:
    """Register a password account; doctor role has no clinical authority yet."""

    limiter: RateLimiter = request.app.state.rate_limiter
    fingerprint = _username_fingerprint(request, payload.username)
    await limiter.check(tenant_id=_ACCOUNT_TENANT, actor_id=f"register_{fingerprint[:24]}")
    repository = SqlAlchemyAccountRepository(session)
    actor_id = f"usr_account_{uuid.uuid4().hex}"
    try:
        user = await repository.create(
            tenant_id=_ACCOUNT_TENANT,
            actor_id=actor_id,
            role=payload.role,
            username_fingerprint=fingerprint,
            username=payload.username.strip(),
            password_hash=hash_password(payload.password),
        )
    except AccountConflictError as error:
        await repository.record_security_event(
            tenant_id=_ACCOUNT_TENANT,
            subject_fingerprint=fingerprint,
            event_type="register",
            outcome="rejected",
        )
        await session.commit()
        raise HTTPException(status_code=409, detail={"code": "ACCOUNT_UNAVAILABLE"}) from error
    result = await _issue_account_session(
        request, repository, user_id=user.id, actor_id=actor_id, account_role=payload.role
    )
    await repository.record_security_event(
        tenant_id=_ACCOUNT_TENANT,
        subject_fingerprint=fingerprint,
        event_type="register",
        outcome="succeeded",
        actor_id=actor_id,
        role=payload.role,
    )
    await session.commit()
    return result


@router.post("/login", response_model=AccountSessionRead)
async def login_account(
    payload: AccountLoginRequest,
    request: Request,
    session: AccountSessionDependency,
) -> AccountSessionRead:
    """Verify one local account with an enumeration-safe public failure."""

    limiter: RateLimiter = request.app.state.rate_limiter
    fingerprint = _username_fingerprint(request, payload.username)
    await limiter.check(tenant_id=_ACCOUNT_TENANT, actor_id=f"login_{fingerprint[:24]}")
    repository = SqlAlchemyAccountRepository(session)
    try:
        user, credential = await repository.find_by_username(
            tenant_id=_ACCOUNT_TENANT, username_fingerprint=fingerprint
        )
    except AccountNotFoundError as error:
        await repository.record_security_event(
            tenant_id=_ACCOUNT_TENANT,
            subject_fingerprint=fingerprint,
            event_type="login",
            outcome="rejected",
        )
        await session.commit()
        raise HTTPException(status_code=401, detail={"code": "ACCOUNT_LOGIN_INVALID"}) from error
    if not verify_password(payload.password, credential.password_hash):
        await repository.record_security_event(
            tenant_id=_ACCOUNT_TENANT,
            subject_fingerprint=fingerprint,
            event_type="login",
            outcome="rejected",
            actor_id=user.external_id,
            role=cast(Literal["patient", "doctor", "admin"], user.role),
        )
        await session.commit()
        raise HTTPException(status_code=401, detail={"code": "ACCOUNT_LOGIN_INVALID"})
    role = cast(Literal["patient", "doctor", "admin"], user.role)
    result = await _issue_account_session(
        request, repository, user_id=user.id, actor_id=user.external_id, account_role=role
    )
    await repository.record_security_event(
        tenant_id=_ACCOUNT_TENANT,
        subject_fingerprint=fingerprint,
        event_type="login",
        outcome="succeeded",
        actor_id=user.external_id,
        role=role,
    )
    await session.commit()
    return result


@router.post("/refresh", response_model=AccountSessionRead)
async def refresh_account_session(
    payload: AccountRefreshRequest,
    request: Request,
    session: AccountSessionDependency,
) -> AccountSessionRead:
    """Rotate a one-time opaque refresh token; replay is rejected after rotation."""

    limiter: RateLimiter = request.app.state.rate_limiter
    token_fingerprint = audit_hmac_digest(
        request.app.state.settings.auth_jwt_secret.get_secret_value().encode(),
        f"local-account-refresh:v1:{payload.refresh_token}".encode(),
    )
    await limiter.check(tenant_id=_ACCOUNT_TENANT, actor_id=f"refresh_{token_fingerprint[:24]}")
    repository = SqlAlchemyAccountRepository(session)
    try:
        previous, user = await repository.lock_refresh_session(token_fingerprint=token_fingerprint)
    except AccountNotFoundError as error:
        await repository.record_security_event(
            tenant_id=_ACCOUNT_TENANT,
            subject_fingerprint=token_fingerprint,
            event_type="refresh",
            outcome="rejected",
        )
        await session.commit()
        raise HTTPException(status_code=401, detail={"code": "ACCOUNT_REFRESH_INVALID"}) from error
    role = cast(Literal["patient", "doctor", "admin"], user.role)
    result = await _issue_account_session(
        request, repository, user_id=user.id, actor_id=user.external_id, account_role=role
    )
    await repository.revoke_refresh_session(previous)
    await repository.record_security_event(
        tenant_id=_ACCOUNT_TENANT,
        subject_fingerprint=token_fingerprint,
        event_type="refresh",
        outcome="succeeded",
        actor_id=user.external_id,
        role=role,
    )
    await session.commit()
    return result


@router.post("/switch-view", response_model=AccountSessionRead)
async def switch_administrator_view(
    payload: AccountViewRoleRequest,
    request: Request,
    session: AccountSessionDependency,
    identity: Annotated[AuthContext, Depends(require_account_admin)],
) -> AccountSessionRead:
    """Issue a fresh administrator session for a patient or doctor workspace.

    The account remains `admin`; only the server-issued runtime/presentation role
    changes.  No patient or doctor data is adopted by this operation.
    """

    repository = SqlAlchemyAccountRepository(session)
    try:
        user, _credential = await repository.lock_account_by_actor(
            tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except AccountNotFoundError as error:
        raise HTTPException(status_code=403, detail={"code": "ACCOUNT_ADMIN_REQUIRED"}) from error
    if user.role != "admin" or not user.is_active:
        raise HTTPException(status_code=403, detail={"code": "ACCOUNT_ADMIN_REQUIRED"})
    result = await _issue_account_session(
        request,
        repository,
        user_id=user.id,
        actor_id=user.external_id,
        account_role="admin",
        active_role=payload.role,
    )
    await repository.record_security_event(
        tenant_id=identity.tenant_id,
        subject_fingerprint=_opaque_subject_fingerprint(
            request, namespace="actor", value=identity.actor_id
        ),
        event_type="admin_update",
        outcome="succeeded",
        actor_id=identity.actor_id,
        role="admin",
    )
    await session.commit()
    return result


@router.get("/admin/accounts", response_model=AccountAdminListRead)
async def list_accounts_for_administrator(
    request: Request,
    session: AccountSessionDependency,
    identity: Annotated[AuthContext, Depends(require_account_admin)],
    limit: int = Query(default=50, ge=1, le=100),
    after_actor_id: str | None = Query(default=None, pattern=r"^usr_account_[a-f0-9]{32}$"),
) -> AccountAdminListRead:
    """List only this tenant's account directory for the verified administrator."""

    del request
    entries = await SqlAlchemyAccountRepository(session).list_accounts(
        tenant_id=identity.tenant_id, limit=limit + 1, after_actor_id=after_actor_id
    )
    has_more = len(entries) > limit
    visible = entries[:limit]
    return AccountAdminListRead(
        accounts=[
            AccountAdminRead(
                actor_id=user.external_id,
                username=credential.username,
                role=cast(Literal["patient", "doctor", "admin"], user.role),
                is_active=user.is_active,
                created_at=user.created_at,
            )
            for user, credential in visible
        ],
        next_after_actor_id=visible[-1][0].external_id if has_more and visible else None,
    )


@router.patch("/admin/accounts/{actor_id}", response_model=AccountAdminRead)
async def update_account_for_administrator(
    actor_id: str,
    payload: AccountAdminUpdateRequest,
    request: Request,
    session: AccountSessionDependency,
    identity: Annotated[AuthContext, Depends(require_account_admin)],
) -> AccountAdminRead:
    """Change patient/doctor role or active status and immediately revoke sessions."""

    repository = SqlAlchemyAccountRepository(session)
    if actor_id == identity.actor_id:
        raise HTTPException(status_code=409, detail={"code": "ACCOUNT_SELF_MANAGEMENT_FORBIDDEN"})
    try:
        user, credential = await repository.lock_account_by_actor(
            tenant_id=identity.tenant_id, actor_id=actor_id
        )
    except AccountNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "ACCOUNT_NOT_FOUND"}) from error
    if user.role == "admin":
        raise HTTPException(status_code=403, detail={"code": "ACCOUNT_ADMIN_TARGET_FORBIDDEN"})
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    await repository.revoke_all_refresh_sessions(user_id=user.id)
    await repository.record_security_event(
        tenant_id=identity.tenant_id,
        subject_fingerprint=_opaque_subject_fingerprint(request, namespace="actor", value=actor_id),
        event_type="admin_update",
        outcome="succeeded",
        actor_id=identity.actor_id,
        role="admin",
    )
    await request.app.state.redis.set(account_access_revocation_key(actor_id), "1", ex=900)
    await session.commit()
    return AccountAdminRead(
        actor_id=user.external_id,
        username=credential.username,
        role=cast(Literal["patient", "doctor", "admin"], user.role),
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get("/admin/bad-cases", response_model=BadCaseAdminListRead)
async def list_bad_cases_for_administrator(
    session: AccountSessionDependency,
    identity: Annotated[AuthContext, Depends(require_account_admin)],
    status_filter: Literal["open", "triaged", "resolved", "dismissed"] | None = Query(
        default=None, alias="status"
    ),
    limit: int = Query(default=50, ge=1, le=100),
) -> BadCaseAdminListRead:
    """List bounded tenant review metadata without decrypting user snapshots."""

    # ``snapshot`` is intentionally excluded from the administrative queue.
    # Besides avoiding an unnecessary decrypt of PHI, this keeps the review
    # metadata usable when an old encrypted snapshot can no longer be read.
    statement = (
        select(BadCase)
        .options(defer(BadCase.snapshot))
        .where(BadCase.tenant_id == identity.tenant_id)
    )
    if status_filter is not None:
        statement = statement.where(BadCase.status == status_filter)
    statement = statement.order_by(BadCase.created_at.desc(), BadCase.id.desc()).limit(limit)
    entries = (await session.scalars(statement)).all()
    return BadCaseAdminListRead(cases=[BadCaseAdminRead.model_validate(item) for item in entries])


@router.patch("/admin/bad-cases/{case_id}", response_model=BadCaseAdminRead)
async def update_bad_case_for_administrator(
    case_id: uuid.UUID,
    payload: BadCaseAdminUpdateRequest,
    request: Request,
    session: AccountSessionDependency,
    identity: Annotated[AuthContext, Depends(require_account_admin)],
) -> BadCaseAdminRead:
    """Record bounded review state; comments/snapshots remain outside this API."""

    statement = (
        select(BadCase)
        .options(defer(BadCase.snapshot))
        .where(BadCase.tenant_id == identity.tenant_id, BadCase.id == case_id)
        .with_for_update()
    )
    item = await session.scalar(statement)
    if item is None:
        raise HTTPException(status_code=404, detail={"code": "BAD_CASE_NOT_FOUND"})
    item.status = payload.status
    item.resolved_at = datetime.now(UTC) if payload.status in {"resolved", "dismissed"} else None
    await SqlAlchemyAccountRepository(session).record_security_event(
        tenant_id=identity.tenant_id,
        subject_fingerprint=_opaque_subject_fingerprint(
            request, namespace="bad-case", value=str(case_id)
        ),
        event_type="admin_update",
        outcome="succeeded",
        actor_id=identity.actor_id,
        role="admin",
    )
    await session.commit()
    return BadCaseAdminRead.model_validate(item)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_account_session(
    payload: AccountRefreshRequest,
    request: Request,
    session: AccountSessionDependency,
) -> None:
    """Idempotently revoke one opaque refresh token without exposing its state."""

    token_fingerprint = audit_hmac_digest(
        request.app.state.settings.auth_jwt_secret.get_secret_value().encode(),
        f"local-account-refresh:v1:{payload.refresh_token}".encode(),
    )
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=_ACCOUNT_TENANT, actor_id=f"logout_{token_fingerprint[:24]}")
    repository = SqlAlchemyAccountRepository(session)
    try:
        previous, user = await repository.lock_refresh_session(token_fingerprint=token_fingerprint)
    except AccountNotFoundError:
        await repository.record_security_event(
            tenant_id=_ACCOUNT_TENANT,
            subject_fingerprint=token_fingerprint,
            event_type="logout",
            outcome="ignored",
        )
        await session.commit()
        return None
    await repository.revoke_refresh_session(previous)
    await repository.record_security_event(
        tenant_id=_ACCOUNT_TENANT,
        subject_fingerprint=token_fingerprint,
        event_type="logout",
        outcome="succeeded",
        actor_id=user.external_id,
        role=cast(Literal["patient", "doctor", "admin"], user.role),
    )
    await session.commit()


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_account_password(
    payload: AccountPasswordChangeRequest,
    request: Request,
    session: AccountSessionDependency,
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> None:
    """Change one authenticated account password and revoke all refresh sessions."""

    if identity.account_role not in {"patient", "doctor", "admin"}:
        raise HTTPException(status_code=403, detail={"code": "ACCOUNT_REQUIRED"})
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)
    repository = SqlAlchemyAccountRepository(session)
    try:
        user, credential = await repository.lock_credential_by_actor(
            tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except AccountNotFoundError as error:
        await repository.record_security_event(
            tenant_id=identity.tenant_id,
            subject_fingerprint=_opaque_subject_fingerprint(
                request, namespace="actor", value=identity.actor_id
            ),
            event_type="password_change",
            outcome="rejected",
            actor_id=identity.actor_id,
        )
        await session.commit()
        raise HTTPException(status_code=403, detail={"code": "ACCOUNT_REQUIRED"}) from error
    if not verify_password(payload.current_password, credential.password_hash):
        await repository.record_security_event(
            tenant_id=identity.tenant_id,
            subject_fingerprint=_opaque_subject_fingerprint(
                request, namespace="actor", value=identity.actor_id
            ),
            event_type="password_change",
            outcome="rejected",
            actor_id=identity.actor_id,
            role=cast(Literal["patient", "doctor", "admin"], user.role),
        )
        await session.commit()
        raise HTTPException(status_code=401, detail={"code": "ACCOUNT_PASSWORD_INVALID"})
    credential.password_hash = hash_password(payload.new_password)
    credential.password_version += 1
    await repository.revoke_all_refresh_sessions(user_id=user.id)
    await repository.record_security_event(
        tenant_id=identity.tenant_id,
        subject_fingerprint=_opaque_subject_fingerprint(
            request, namespace="actor", value=identity.actor_id
        ),
        event_type="password_change",
        outcome="succeeded",
        actor_id=identity.actor_id,
        role=cast(Literal["patient", "doctor", "admin"], user.role),
    )
    await session.commit()


@router.post("/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_account(
    payload: AccountDeactivationRequest,
    request: Request,
    session: AccountSessionDependency,
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> None:
    """Disable the caller's local sign-in and revoke every refresh session.

    This does not delete clinical data or make any data-retention promise. A
    disabled credential cannot refresh, log in, or use a new authenticated API
    request after the current short-lived access token expires.
    """

    is_account = identity.actor_id.startswith("usr_account_")
    if identity.account_role not in {"patient", "doctor", "admin"} or not is_account:
        raise HTTPException(status_code=403, detail={"code": "ACCOUNT_REQUIRED"})
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)
    repository = SqlAlchemyAccountRepository(session)
    subject_fingerprint = _opaque_subject_fingerprint(
        request, namespace="actor", value=identity.actor_id
    )
    try:
        user, credential = await repository.lock_credential_by_actor(
            tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except AccountNotFoundError as error:
        await repository.record_security_event(
            tenant_id=identity.tenant_id,
            subject_fingerprint=subject_fingerprint,
            event_type="deactivate",
            outcome="rejected",
            actor_id=identity.actor_id,
        )
        await session.commit()
        raise HTTPException(status_code=403, detail={"code": "ACCOUNT_REQUIRED"}) from error
    if not verify_password(payload.current_password, credential.password_hash):
        await repository.record_security_event(
            tenant_id=identity.tenant_id,
            subject_fingerprint=subject_fingerprint,
            event_type="deactivate",
            outcome="rejected",
            actor_id=identity.actor_id,
            role=cast(Literal["patient", "doctor", "admin"], user.role),
        )
        await session.commit()
        raise HTTPException(status_code=401, detail={"code": "ACCOUNT_PASSWORD_INVALID"})
    await repository.revoke_all_refresh_sessions(user_id=user.id)
    await repository.deactivate_user(user)
    await repository.record_security_event(
        tenant_id=identity.tenant_id,
        subject_fingerprint=subject_fingerprint,
        event_type="deactivate",
        outcome="succeeded",
        actor_id=identity.actor_id,
        role=cast(Literal["patient", "doctor", "admin"], user.role),
    )
    # Account access tokens have a fixed 15-minute lifetime. Marking the
    # caller revoked before committing the relational state makes any stale
    # short-lived token fail closed immediately across all API routes.
    await request.app.state.redis.set(account_access_revocation_key(identity.actor_id), "1", ex=900)
    await session.commit()


@router.post("/guest", response_model=GuestTokenRead)
async def issue_guest_token(request: Request) -> GuestTokenRead:
    """Issue a session-local, pseudonymous patient credential for Trace/bad-case evidence."""

    settings = request.app.state.settings
    visitor_id = request.headers.get("X-GerClaw-Visitor-ID", "")
    visitor_signature = request.headers.get("X-GerClaw-Visitor-Signature", "")
    expected = hmac.new(
        settings.guest_identity_secret.get_secret_value().encode(),
        f"gerclaw-guest-bootstrap:v1:{visitor_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    valid_identity = (
        _VISITOR_ID.fullmatch(visitor_id) is not None
        and _VISITOR_SIGNATURE.fullmatch(visitor_signature) is not None
        and hmac.compare_digest(visitor_signature, expected)
    )
    if not valid_identity:
        raise HTTPException(status_code=403, detail={"code": "GUEST_IDENTITY_INVALID"})
    limiter: RateLimiter = request.app.state.rate_limiter
    secret = settings.guest_identity_secret.get_secret_value().encode()
    digest = hmac.new(secret, visitor_id.encode(), hashlib.sha256).hexdigest()
    await limiter.check(tenant_id=_ACCOUNT_TENANT, actor_id=f"guest_{digest[:24]}")
    actor_suffix = hmac.new(
        settings.guest_identity_secret.get_secret_value().encode(),
        f"gerclaw-guest-actor:v2:{visitor_id}".encode(),
        hashlib.sha256,
    ).hexdigest()[:32]
    actor_id = f"usr_guest_{actor_suffix}"
    token = create_access_token(
        settings,
        actor_id=actor_id,
        tenant_id=_ACCOUNT_TENANT,
        scopes=_guest_scopes(),
        role="guest",
        account_role="guest",
        lifetime_seconds=settings.guest_token_ttl_seconds,
    )
    return GuestTokenRead(
        access_token=token,
        expires_in=settings.guest_token_ttl_seconds,
        actor_id=actor_id,
    )

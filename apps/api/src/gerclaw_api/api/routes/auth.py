"""Pseudonymous visitor bootstrap for login-free product access."""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import AuthContext, authenticate, create_access_token
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

_GUEST_SCOPES = {
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
    """Short-lived bearer credential returned only to the trusted BFF."""

    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(min_length=32)
    token_type: str = "bearer"
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


class AccountSessionRead(BaseModel):
    """Tokens are returned to the same-origin BFF, never persisted by the API."""

    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(min_length=32)
    refresh_token: str = Field(min_length=32)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(ge=300, le=86_400)
    actor_id: str = Field(pattern=r"^usr_account_[a-f0-9]{32}$")
    role: Literal["patient", "doctor"]


class AccountIdentityRead(BaseModel):
    """Verified current account identity, intentionally without credentials."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str = Field(pattern=r"^usr_account_[a-f0-9]{32}$")
    role: Literal["patient", "doctor"]


def _account_scopes() -> set[str]:
    """Account role is not a substitute for patient or clinical authorisation."""

    return set(_GUEST_SCOPES)


@router.get("/session", response_model=AccountIdentityRead)
async def read_account_session(
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> AccountIdentityRead:
    """Return only the verified account role needed to render the authenticated UI."""

    if identity.role not in {"patient", "doctor"} or not identity.actor_id.startswith(
        "usr_account_"
    ):
        raise HTTPException(status_code=403, detail={"code": "ACCOUNT_REQUIRED"})
    return AccountIdentityRead(actor_id=identity.actor_id, role=identity.role)


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
    role: Literal["patient", "doctor"],
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
            scopes=_account_scopes(),
            role=role,
            lifetime_seconds=900,
        ),
        refresh_token=refresh_token,
        expires_in=900,
        actor_id=actor_id,
        role=role,
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
        request, repository, user_id=user.id, actor_id=actor_id, role=payload.role
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
            role=cast(Literal["patient", "doctor"], user.role),
        )
        await session.commit()
        raise HTTPException(status_code=401, detail={"code": "ACCOUNT_LOGIN_INVALID"})
    role = cast(Literal["patient", "doctor"], user.role)
    result = await _issue_account_session(
        request, repository, user_id=user.id, actor_id=user.external_id, role=role
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
    role = cast(Literal["patient", "doctor"], user.role)
    result = await _issue_account_session(
        request, repository, user_id=user.id, actor_id=user.external_id, role=role
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
        role=cast(Literal["patient", "doctor"], user.role),
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

    if identity.role not in {"patient", "doctor"}:
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
            role=cast(Literal["patient", "doctor"], user.role),
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
        role=cast(Literal["patient", "doctor"], user.role),
    )
    await session.commit()


@router.post("/guest", response_model=GuestTokenRead)
async def issue_guest_token(request: Request) -> GuestTokenRead:
    """Issue an opaque, least-privilege visitor identity after rate limiting."""

    settings = request.app.state.settings
    peer = request.client.host if request.client is not None else "unknown"
    visitor_id = request.headers.get("X-GerClaw-Visitor-ID", "")
    visitor_signature = request.headers.get("X-GerClaw-Visitor-Signature", "")
    signature_payload = f"gerclaw-guest-bootstrap:v1:{visitor_id}"
    identity_secret = settings.guest_identity_secret.get_secret_value().encode()
    expected_signature = hmac.new(
        identity_secret,
        signature_payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    has_valid_bff_identity = (
        _VISITOR_ID.fullmatch(visitor_id) is not None
        and _VISITOR_SIGNATURE.fullmatch(visitor_signature) is not None
        and hmac.compare_digest(visitor_signature, expected_signature)
    )
    rate_material = f"visitor:{visitor_id}" if has_valid_bff_identity else f"peer:{peer}"
    rate_identity = hmac.new(
        identity_secret,
        rate_material.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id="tenant_public0001", actor_id=f"auth_{rate_identity}")
    if has_valid_bff_identity:
        actor_material = f"gerclaw-guest-actor:v1:{visitor_id}"
        actor_suffix = hmac.new(
            identity_secret,
            actor_material.encode(),
            hashlib.sha256,
        ).hexdigest()[:32]
    else:
        actor_suffix = uuid.uuid4().hex
    actor_id = f"usr_guest_{actor_suffix}"
    token = create_access_token(
        settings,
        actor_id=actor_id,
        tenant_id="tenant_public0001",
        scopes=_GUEST_SCOPES,
        lifetime_seconds=settings.guest_token_ttl_seconds,
    )
    return GuestTokenRead(
        access_token=token,
        expires_in=settings.guest_token_ttl_seconds,
        actor_id=actor_id,
    )

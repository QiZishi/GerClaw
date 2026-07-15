"""Strict tenant-scoped JWT authentication for internal and guest principals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from gerclaw_api.config import Settings
from gerclaw_api.domain.trace_schemas import SAFE_IDENTIFIER_PATTERN
from gerclaw_api.security import redact_text

bearer_scheme = HTTPBearer(auto_error=False)


class AuthContext(BaseModel):
    """Identity and scopes derived only from a verified bearer token."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    tenant_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    scopes: frozenset[str]

    @field_validator("actor_id", "tenant_id")
    @classmethod
    def reject_pii_identifiers(cls, value: str) -> str:
        if redact_text(value) != value:
            raise ValueError("identity claims must be opaque and cannot contain PII")
        return value


def create_access_token(
    settings: Settings,
    *,
    actor_id: str,
    tenant_id: str,
    scopes: set[str],
    lifetime_seconds: int = 300,
) -> str:
    """Issue a short-lived HS256 token for a trusted identity provider or test harness."""

    now = datetime.now(UTC)
    claims = {
        "sub": actor_id,
        "tenant_id": tenant_id,
        "scope": " ".join(sorted(scopes)),
        "iss": settings.auth_jwt_issuer,
        "aud": settings.auth_jwt_audience,
        "iat": now,
        "exp": now + timedelta(seconds=lifetime_seconds),
    }
    return jwt.encode(
        claims,
        settings.auth_jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


async def authenticate(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthContext:
    """Verify a fixed-algorithm JWT and derive tenant/actor identity."""

    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "valid bearer token required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings: Settings = request.app.state.settings
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.auth_jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.auth_jwt_audience,
            issuer=settings.auth_jwt_issuer,
            options={"require": ["sub", "tenant_id", "scope", "iat", "exp"]},
        )
        scope_value = claims["scope"]
        if not isinstance(scope_value, str):
            raise InvalidTokenError("scope must be a space-delimited string")
        return AuthContext(
            actor_id=claims["sub"],
            tenant_id=claims["tenant_id"],
            scopes=frozenset(scope_value.split()),
        )
    except (InvalidTokenError, KeyError, ValidationError, TypeError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": "bearer token is invalid or expired"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def _authorize(identity: AuthContext, required_scope: str) -> AuthContext:
    if required_scope not in identity.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AUTH_SCOPE_REQUIRED", "message": f"missing {required_scope} scope"},
        )
    return identity


async def require_trace_read(
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> AuthContext:
    """Require tenant-scoped Trace read access."""

    return _authorize(identity, "trace:read")


async def require_trace_write(
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> AuthContext:
    """Require tenant-scoped Trace mutation access."""

    return _authorize(identity, "trace:write")


async def require_feedback_write(
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> AuthContext:
    """Require tenant-scoped feedback mutation access."""

    return _authorize(identity, "feedback:write")


async def require_metrics_read(
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> AuthContext:
    """Require operational metrics access."""

    return _authorize(identity, "metrics:read")


async def require_rag_read(
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> AuthContext:
    """Require access to local medical evidence retrieval."""

    return _authorize(identity, "rag:read")


async def require_chat_read(
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> AuthContext:
    """Require access to the caller's own conversation history."""

    return _authorize(identity, "chat:read")


async def require_chat_write(
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> AuthContext:
    """Require access to execute a tenant-scoped Agent turn."""

    return _authorize(identity, "chat:write")


async def require_memory_read(
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> AuthContext:
    """Require access to the caller's own encrypted health memory."""

    return _authorize(identity, "memory:read")


async def require_memory_write(
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> AuthContext:
    """Require confirmation or retirement of the caller's memory facts."""

    return _authorize(identity, "memory:write")


async def require_search_read(
    identity: Annotated[AuthContext, Depends(authenticate)],
) -> AuthContext:
    """Require access to provider-backed online evidence search."""

    return _authorize(identity, "search:read")

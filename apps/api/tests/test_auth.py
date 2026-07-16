"""JWT verification, scope authorization, and opaque identity tests."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

from gerclaw_api.auth import (
    AuthContext,
    authenticate,
    create_access_token,
    require_clinical_intake_read,
    require_clinical_intake_write,
    require_feedback_write,
    require_memory_read,
    require_memory_write,
    require_metrics_read,
    require_trace_read,
    require_trace_write,
)
from tests.conftest import make_settings


def _request() -> tuple[Request, object]:
    settings = make_settings()
    app = SimpleNamespace(state=SimpleNamespace(settings=settings))
    return Request({"type": "http", "app": app}), settings


@pytest.mark.asyncio
async def test_authentication_verifies_claims_and_scopes() -> None:
    request, settings = _request()
    token = create_access_token(
        settings,
        actor_id="usr_patient_auth0001",
        tenant_id="tenant_public0001",
        scopes={
            "trace:read",
            "trace:write",
            "feedback:write",
            "metrics:read",
            "memory:read",
            "memory:write",
            "clinical_intake:read",
            "clinical_intake:write",
        },
    )
    identity = await authenticate(
        request,
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
    )

    assert await require_trace_read(identity) is identity
    assert await require_trace_write(identity) is identity
    assert await require_feedback_write(identity) is identity
    assert await require_metrics_read(identity) is identity
    assert await require_memory_read(identity) is identity
    assert await require_memory_write(identity) is identity
    assert await require_clinical_intake_read(identity) is identity
    assert await require_clinical_intake_write(identity) is identity


@pytest.mark.asyncio
async def test_authentication_rejects_missing_expired_and_insufficient_tokens() -> None:
    request, settings = _request()
    with pytest.raises(HTTPException) as missing:
        await authenticate(request, None)
    assert missing.value.status_code == 401

    expired = create_access_token(
        settings,
        actor_id="usr_patient_auth0001",
        tenant_id="tenant_public0001",
        scopes={"trace:read"},
        lifetime_seconds=-1,
    )
    with pytest.raises(HTTPException) as invalid:
        await authenticate(
            request,
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired),
        )
    assert invalid.value.status_code == 401

    identity = AuthContext(
        actor_id="usr_patient_auth0001",
        tenant_id="tenant_public0001",
        scopes=frozenset({"trace:read"}),
    )
    with pytest.raises(HTTPException) as forbidden:
        await require_trace_write(identity)
    assert forbidden.value.status_code == 403


def test_auth_context_rejects_phone_or_email_identifiers() -> None:
    with pytest.raises(ValidationError):
        AuthContext(
            actor_id="usr_13800138000",
            tenant_id="tenant_public0001",
            scopes=frozenset(),
        )
    with pytest.raises(ValidationError):
        AuthContext(
            actor_id="usr_patient_auth0001",
            tenant_id="tenant_patient@example.com",
            scopes=frozenset(),
        )

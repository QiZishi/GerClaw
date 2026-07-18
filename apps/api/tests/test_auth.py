"""JWT verification, scope authorization, and opaque identity tests."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

from gerclaw_api.api.routes.auth import _account_scopes, read_account_session
from gerclaw_api.auth import (
    AuthContext,
    account_access_revocation_key,
    authenticate,
    create_access_token,
    require_clinical_intake_read,
    require_clinical_intake_write,
    require_feedback_write,
    require_memory_read,
    require_memory_write,
    require_metrics_read,
    require_risk_alert_read,
    require_risk_alert_write,
    require_trace_read,
    require_trace_write,
    require_voice_use,
)
from tests.conftest import make_settings


def _request() -> tuple[Request, object]:
    settings = make_settings()
    app = SimpleNamespace(state=SimpleNamespace(settings=settings))
    return Request({"type": "http", "app": app}), settings


class _Redis:
    def __init__(self, revoked: set[str] | None = None) -> None:
        self.revoked = revoked or set()

    async def exists(self, key: str) -> int:
        return int(key in self.revoked)


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
            "voice:use",
            "risk_alert:read",
            "risk_alert:write",
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
    assert await require_voice_use(identity) is identity
    assert await require_risk_alert_read(identity) is identity
    assert await require_risk_alert_write(identity) is identity


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


@pytest.mark.asyncio
async def test_account_session_read_only_accepts_verified_account_identity() -> None:
    account = AuthContext(
        actor_id="usr_account_0123456789abcdef0123456789abcdef",
        tenant_id="tenant_public0001",
        role="patient",
        scopes=frozenset(),
    )
    identity = await read_account_session(account)
    assert identity.actor_id == account.actor_id
    assert identity.role == "patient"

    with pytest.raises(HTTPException) as denied:
        await read_account_session(
            AuthContext(
                actor_id="usr_guest_0123456789abcdef0123456789abcdef",
                tenant_id="tenant_public0001",
                role="guest",
                scopes=frozenset(),
            )
        )
    assert denied.value.status_code == 403
    with pytest.raises(ValidationError):
        AuthContext(
            actor_id="usr_patient_auth0001",
            tenant_id="tenant_patient@example.com",
            scopes=frozenset(),
        )


def test_only_clinician_and_administrator_accounts_receive_runtime_decision_scope() -> None:
    assert "approval:decide" not in _account_scopes("patient")
    assert "approval:decide" in _account_scopes("doctor")
    assert "approval:decide" in _account_scopes("admin")


@pytest.mark.asyncio
async def test_account_access_token_is_fail_closed_when_revoked_or_verifier_missing() -> None:
    request, settings = _request()
    actor_id = "usr_account_0123456789abcdef0123456789abcdef"
    token = create_access_token(
        settings,
        actor_id=actor_id,
        tenant_id="tenant_public0001",
        role="patient",
        scopes={"chat:read"},
    )
    request.app.state.redis = _Redis()
    identity = await authenticate(
        request, HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    )
    assert identity.actor_id == actor_id

    request.app.state.redis = _Redis({account_access_revocation_key(actor_id)})
    with pytest.raises(HTTPException) as revoked:
        await authenticate(
            request, HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )
    assert revoked.value.status_code == 401

    del request.app.state.redis
    with pytest.raises(HTTPException) as missing_verifier:
        await authenticate(
            request, HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )
    assert missing_verifier.value.status_code == 401

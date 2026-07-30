"""Fast, dependency-free checks for visitor bootstrap and Skill error boundaries."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from types import SimpleNamespace
from typing import Any, cast

import jwt
import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.api.routes import skills as skill_routes
from gerclaw_api.application import create_app
from gerclaw_api.auth import AuthContext
from gerclaw_api.config import Settings
from gerclaw_api.modules.skill import (
    SkillDraftQualityReport,
    SkillEvolutionDecision,
    SkillEvolutionRequest,
    UnsafeSkillError,
)
from gerclaw_api.modules.skill.security import SkillSafetyFinding


class _RateLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def check(self, *, tenant_id: str, actor_id: str) -> None:
        self.calls.append((tenant_id, actor_id))


class _RollbackSession:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def rollback(self) -> None:
        self._events.append("rollback")


class _FailingEvolutionModule:
    def __init__(self, error: BaseException) -> None:
        self._error = error

    async def evolve_skill_from_nl(self, *_args: Any, **_kwargs: Any) -> None:
        raise self._error


@pytest.mark.asyncio
async def test_guest_bootstrap_uses_peer_rate_identity_and_least_privilege_token(
    unit_settings: Settings,
) -> None:
    app = create_app(unit_settings)
    limiter = _RateLimiter()
    app.state.rate_limiter = limiter
    visitor_id = "a" * 32
    signature = hmac.new(
        unit_settings.guest_identity_secret.get_secret_value().encode(),
        f"gerclaw-guest-bootstrap:v1:{visitor_id}".encode(),
        hashlib.sha256,
    ).hexdigest()

    @app.get("/_test/unsafe-skill")
    async def unsafe_skill(_request: Request) -> None:
        raise UnsafeSkillError([SkillSafetyFinding(code="ROLE_OVERRIDE", field="source_markdown")])

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("203.0.113.8", 43100)),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/auth/guest",
            headers={
                "X-GerClaw-Visitor-ID": visitor_id,
                "X-GerClaw-Visitor-Signature": signature,
            },
        )
        rejected = await client.get("/_test/unsafe-skill")

    assert response.status_code == 200, response.text
    payload = response.json()
    claims = jwt.decode(
        payload["access_token"],
        unit_settings.auth_jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=unit_settings.auth_jwt_audience,
        issuer=unit_settings.auth_jwt_issuer,
    )
    assert claims["sub"] == payload["actor_id"]
    assert claims["tenant_id"] == "tenant_public0001"
    assert "skill:read" not in claims["scope"].split()
    assert "skill:write" not in claims["scope"].split()
    assert "skill:execute" not in claims["scope"].split()
    assert "metrics:read" not in claims["scope"].split()
    assert limiter.calls[0][0] == "tenant_public0001"
    assert limiter.calls[0][1].startswith("guest_")
    assert "203.0.113.8" not in limiter.calls[0][1]
    assert rejected.status_code == 422
    assert rejected.json() == {
        "error": {
            "code": "SKILL_UNSAFE",
            "message": "Skill rejected by safety policy: ROLE_OVERRIDE",
        }
    }


@pytest.mark.asyncio
async def test_guest_bootstrap_uses_only_a_valid_bff_signed_visitor_identity(
    unit_settings: Settings,
) -> None:
    app = create_app(unit_settings)
    limiter = _RateLimiter()
    app.state.rate_limiter = limiter
    visitor_id = "a" * 32
    signature = hmac.new(
        unit_settings.guest_identity_secret.get_secret_value().encode(),
        f"gerclaw-guest-bootstrap:v1:{visitor_id}".encode(),
        hashlib.sha256,
    ).hexdigest()

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("203.0.113.8", 43100)),
        base_url="http://testserver",
    ) as client:
        signed = await client.post(
            "/api/v1/auth/guest",
            headers={
                "X-GerClaw-Visitor-ID": visitor_id,
                "X-GerClaw-Visitor-Signature": signature,
            },
        )
        refreshed = await client.post(
            "/api/v1/auth/guest",
            headers={
                "X-GerClaw-Visitor-ID": visitor_id,
                "X-GerClaw-Visitor-Signature": signature,
            },
        )
        forged = await client.post(
            "/api/v1/auth/guest",
            headers={
                "X-GerClaw-Visitor-ID": "b" * 32,
                "X-GerClaw-Visitor-Signature": "0" * 64,
            },
        )

    assert signed.status_code == 200
    assert refreshed.status_code == 200
    assert forged.status_code == 403
    assert signed.json()["actor_id"] == refreshed.json()["actor_id"]
    assert forged.json() == {"detail": {"code": "GUEST_IDENTITY_INVALID"}}
    assert len(limiter.calls) == 2
    assert limiter.calls[0][1] == limiter.calls[1][1]
    assert all(actor_id.startswith("guest_") for _tenant_id, actor_id in limiter.calls)


@pytest.mark.parametrize("error", [RuntimeError("failed after flush"), asyncio.CancelledError()])
@pytest.mark.asyncio
async def test_skill_evolution_rolls_back_before_recording_failure_trace(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    events: list[str] = []
    session = _RollbackSession(events)
    identity = AuthContext(
        actor_id="usr_patient00000001",
        tenant_id="tenant_public0001",
        role="patient",
        scopes=frozenset({"skill:write"}),
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=SimpleNamespace(max_events_per_trace=20))
        )
    )

    async def no_rate_limit(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def start_trace(*_args: Any, **_kwargs: Any) -> str:
        return "trace_skill_evolution_rollback"

    async def finish_trace(*_args: Any, **_kwargs: Any) -> None:
        events.append("finish")

    monkeypatch.setattr(skill_routes, "_rate_limit", no_rate_limit)
    monkeypatch.setattr(skill_routes, "_fingerprint", lambda *_args, **_kwargs: "fingerprint")
    monkeypatch.setattr(skill_routes, "get_trace_service", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(skill_routes, "_start_trace", start_trace)
    monkeypatch.setattr(skill_routes, "_finish_trace", finish_trace)
    monkeypatch.setattr(
        skill_routes,
        "_module",
        lambda *_args, **_kwargs: _FailingEvolutionModule(error),
    )

    with pytest.raises(type(error)):
        await skill_routes.evolve_skill(
            "accessible-summary",
            SkillEvolutionRequest(
                change_request="增加一个受限的低风险格式指令。",
                expected_revision=1,
            ),
            cast(Request, request),
            cast(AsyncSession, session),
            identity,
        )

    assert events == ["rollback", "finish"]


def test_skill_evolution_response_rejects_half_present_online_candidate() -> None:
    decision = SkillEvolutionDecision(
        track="mutable",
        object_kind="skill.presentation",
        authority="presentation_only",
        disposition="manual_review_draft",
        reason_codes=("SKILL_PRESENTATION_DSL_ONLY",),
        expected_revision=1,
    )

    with pytest.raises(ValidationError):
        skill_routes.SkillEvolutionRead(
            trace_id="trace_skill_evolution_contract",
            definition=None,
            quality_report=SkillDraftQualityReport(missing_checks=()),
            decision=decision,
            active_definition=None,
        )

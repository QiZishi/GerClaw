"""Fast, dependency-free checks for visitor bootstrap and Skill error boundaries."""

from __future__ import annotations

import hashlib
import hmac

import jwt
import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from gerclaw_api.application import create_app
from gerclaw_api.config import Settings
from gerclaw_api.modules.skill import UnsafeSkillError
from gerclaw_api.modules.skill.security import SkillSafetyFinding


class _RateLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def check(self, *, tenant_id: str, actor_id: str) -> None:
        self.calls.append((tenant_id, actor_id))


@pytest.mark.asyncio
async def test_guest_bootstrap_uses_peer_rate_identity_and_least_privilege_token(
    unit_settings: Settings,
) -> None:
    app = create_app(unit_settings)
    limiter = _RateLimiter()
    app.state.rate_limiter = limiter

    @app.get("/_test/unsafe-skill")
    async def unsafe_skill(_request: Request) -> None:
        raise UnsafeSkillError([SkillSafetyFinding(code="ROLE_OVERRIDE", field="source_markdown")])

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("203.0.113.8", 43100)),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/api/v1/auth/guest")
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
    assert "skill:read" in claims["scope"].split()
    assert "skill:write" in claims["scope"].split()
    assert "skill:execute" in claims["scope"].split()
    assert "metrics:read" not in claims["scope"].split()
    assert limiter.calls[0][0] == "tenant_public0001"
    assert limiter.calls[0][1].startswith("auth_")
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
    assert forged.status_code == 200
    assert signed.json()["actor_id"] == refreshed.json()["actor_id"]
    assert signed.json()["actor_id"] != forged.json()["actor_id"]
    assert len(limiter.calls) == 3
    assert limiter.calls[0][1] == limiter.calls[1][1]
    assert limiter.calls[0][1] != limiter.calls[2][1]
    assert all(actor_id.startswith("auth_") for _tenant_id, actor_id in limiter.calls)

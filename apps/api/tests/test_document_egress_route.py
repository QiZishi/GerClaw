"""Document-parser egress audit boundary tests without a live provider."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
from httpx import ASGITransport, AsyncClient

from gerclaw_api.application import create_app
from gerclaw_api.auth import create_access_token
from gerclaw_api.dependencies import get_database_session
from tests.conftest import make_settings


class _RateLimiter:
    async def check(self, **_kwargs: str) -> None:
        return None


class _EgressSession:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.commit_count = 0

    def add(self, event: object) -> None:
        if getattr(event, "id", None) is None:
            event.id = uuid.uuid4()  # type: ignore[attr-defined]
        self.events.append(event)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commit_count += 1

    async def scalar(self, statement: Any) -> object | None:
        parameters = statement.compile().params
        requested_id = next(
            (value for value in parameters.values() if isinstance(value, uuid.UUID)), None
        )
        owner_values = {value for value in parameters.values() if isinstance(value, str)}
        return next(
            (
                event
                for event in self.events
                if getattr(event, "id", None) == requested_id
                and getattr(event, "tenant_id", None) in owner_values
                and getattr(event, "actor_id", None) in owner_values
            ),
            None,
        )


def _with_egress_session(app: object, egress_session: _EgressSession) -> None:
    async def dependency() -> AsyncGenerator[_EgressSession, None]:
        yield egress_session

    app.dependency_overrides[get_database_session] = dependency  # type: ignore[attr-defined]


def _token(settings: Any, actor_id: str, scopes: set[str]) -> str:
    return create_access_token(
        settings,
        actor_id=actor_id,
        tenant_id="tenant_public0001",
        scopes=scopes,
    )


@pytest.mark.asyncio
async def test_document_parse_egress_is_owner_bound_and_phi_free() -> None:
    settings = make_settings()
    app = create_app(settings)
    app.state.rate_limiter = _RateLimiter()
    egress_session = _EgressSession()
    _with_egress_session(app, egress_session)
    owner = _token(settings, "usr_patient_document0001", {"document:write"})
    other = _token(settings, "usr_patient_document0002", {"document:write"})

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {owner}"},
    ) as client:
        prepared = await client.post("/api/v1/documents/provider-egress/mineru")
        assert prepared.status_code == 200
        egress_id = prepared.json()["egress_id"]
        finished = await client.post(
            f"/api/v1/documents/provider-egress/mineru/{egress_id}",
            json={"outcome": "succeeded"},
        )
        repeated = await client.post(
            f"/api/v1/documents/provider-egress/mineru/{egress_id}",
            json={"outcome": "failed"},
        )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {other}"},
    ) as client:
        foreign = await client.post(
            f"/api/v1/documents/provider-egress/mineru/{egress_id}",
            json={"outcome": "failed"},
        )

    assert finished.status_code == 204
    assert repeated.status_code == 404
    assert repeated.json()["detail"]["code"] == "DOCUMENT_EGRESS_NOT_FOUND"
    assert foreign.status_code == 404
    assert len(egress_session.events) == 1
    event = cast(Any, egress_session.events[0])
    assert event.tenant_id == "tenant_public0001"
    assert event.actor_id == "usr_patient_document0001"
    assert event.purpose == "external_document_parse"
    assert event.processor == "mineru"
    assert event.policy_version == "document-egress-v1"
    assert event.findings == [
        {"field": "capability_version", "value": settings.mineru_capability_version}
    ]
    assert event.outcome == "succeeded"


@pytest.mark.asyncio
async def test_document_parse_egress_requires_document_write_scope() -> None:
    settings = make_settings()
    app = create_app(settings)
    app.state.rate_limiter = _RateLimiter()
    egress_session = _EgressSession()
    _with_egress_session(app, egress_session)
    token = _token(settings, "usr_patient_document0001", {"chat:write"})

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        response = await client.post("/api/v1/documents/provider-egress/mineru")

    assert response.status_code == 403
    assert egress_session.events == []


@pytest.mark.asyncio
async def test_document_parse_egress_rejects_incompatible_mineru_before_audit_or_provider_use() -> (
    None
):
    settings = make_settings().model_copy(update={"mineru_supports_markdown_export": False})
    app = create_app(settings)
    app.state.rate_limiter = _RateLimiter()
    egress_session = _EgressSession()
    _with_egress_session(app, egress_session)
    token = _token(settings, "usr_patient_document0001", {"document:write"})

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        response = await client.post("/api/v1/documents/provider-egress/mineru")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MINERU_CAPABILITY_UNAVAILABLE"
    assert egress_session.events == []

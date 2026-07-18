"""Patient-to-doctor read consent boundaries without a live database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from gerclaw_api.api.routes import consent as consent_routes
from gerclaw_api.auth import AuthContext
from gerclaw_api.modules.consent.models import PatientAccessGrantCreate, PatientAccessGrantRevoke
from gerclaw_api.repositories.consent import (
    PatientAccessGrantConflictError,
    PatientAccessGrantNotFoundError,
)

PATIENT = "usr_account_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
DOCTOR = "usr_account_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _identity(*, role: str = "patient", scopes: frozenset[str] = frozenset()) -> AuthContext:
    return AuthContext(
        actor_id=PATIENT if role == "patient" else DOCTOR,
        tenant_id="tenant_public0001",
        role=role,  # type: ignore[arg-type]
        account_role=role,  # type: ignore[arg-type]
        scopes=scopes,
    )


def _grant(*, status: str = "active", expires_at: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        doctor_actor_id=DOCTOR,
        resource_scope="health_profile_read",
        status=status,
        expires_at=expires_at or datetime.now(UTC) + timedelta(days=7),
        revision=1,
        granted_at=datetime.now(UTC),
        revoked_at=None,
    )


@pytest.mark.asyncio
async def test_patient_grant_validates_active_doctor_and_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def require_active_doctor(self, **kwargs: object) -> None:
            calls.append(kwargs)

        async def grant(self, **kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            return _grant()

    monkeypatch.setattr(consent_routes, "SqlAlchemyPatientAccessGrantRepository", FakeRepository)
    payload = PatientAccessGrantCreate(
        doctor_actor_id=DOCTOR,
        resource_scopes=("health_profile_read", "cga_report_read"),
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )

    result = await consent_routes.grant_access(
        payload, SimpleNamespace(commit=AsyncMock()), _identity()
    )

    assert len(result.items) == 2
    assert calls[0]["actor_id"] == DOCTOR
    assert {call["resource_scope"] for call in calls[1:]} == {
        "health_profile_read",
        "cga_report_read",
    }

    with pytest.raises(HTTPException) as expired:
        await consent_routes.grant_access(
            payload.model_copy(update={"expires_at": datetime.now(UTC)}),
            SimpleNamespace(commit=AsyncMock()),
            _identity(),
        )
    assert expired.value.detail["code"] == "PATIENT_ACCESS_EXPIRY_INVALID"

    with pytest.raises(ValidationError):
        PatientAccessGrantCreate(
            doctor_actor_id=DOCTOR,
            resource_scopes=("health_profile_read", "health_profile_read"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )


@pytest.mark.asyncio
async def test_only_patient_can_mutate_own_grants() -> None:
    payload = PatientAccessGrantCreate(
        doctor_actor_id=DOCTOR,
        resource_scopes=("health_profile_read",),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    with pytest.raises(HTTPException) as rejected:
        await consent_routes.grant_access(payload, SimpleNamespace(), _identity(role="doctor"))
    assert rejected.value.status_code == 403
    assert rejected.value.detail["code"] == "PATIENT_ACCOUNT_REQUIRED"


@pytest.mark.asyncio
async def test_revoke_is_revision_fenced_and_not_found_is_uniform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _grant()

    class FakeRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def revoke(self, **_kwargs: object) -> SimpleNamespace:
            return record

    monkeypatch.setattr(consent_routes, "SqlAlchemyPatientAccessGrantRepository", FakeRepository)
    result = await consent_routes.revoke_access(
        record.id,
        PatientAccessGrantRevoke(expected_revision=1),
        SimpleNamespace(commit=AsyncMock()),
        _identity(),
    )
    assert result.status == "active"

    class MissingRepository(FakeRepository):
        async def revoke(self, **_kwargs: object) -> SimpleNamespace:
            raise PatientAccessGrantNotFoundError("hidden")

    monkeypatch.setattr(consent_routes, "SqlAlchemyPatientAccessGrantRepository", MissingRepository)
    with pytest.raises(HTTPException) as missing:
        await consent_routes.revoke_access(
            record.id,
            PatientAccessGrantRevoke(expected_revision=1),
            SimpleNamespace(commit=AsyncMock()),
            _identity(),
        )
    assert missing.value.status_code == 404
    assert missing.value.detail["code"] == "PATIENT_ACCESS_NOT_FOUND"

    class ConflictRepository(FakeRepository):
        async def revoke(self, **_kwargs: object) -> SimpleNamespace:
            raise PatientAccessGrantConflictError("stale")

    monkeypatch.setattr(
        consent_routes, "SqlAlchemyPatientAccessGrantRepository", ConflictRepository
    )
    with pytest.raises(HTTPException) as conflict:
        await consent_routes.revoke_access(
            record.id,
            PatientAccessGrantRevoke(expected_revision=1),
            SimpleNamespace(commit=AsyncMock()),
            _identity(),
        )
    assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_doctor_projections_fail_closed_without_current_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def require_active_grant(self, **_kwargs: object) -> None:
            raise PatientAccessGrantNotFoundError("hidden")

    monkeypatch.setattr(consent_routes, "SqlAlchemyPatientAccessGrantRepository", MissingRepository)
    doctor = _identity(role="doctor", scopes=frozenset({"memory:read", "cga:read"}))
    for endpoint in (
        consent_routes.get_authorized_health_profile,
        consent_routes.list_authorized_cga_reports,
    ):
        with pytest.raises(HTTPException) as denied:
            if endpoint is consent_routes.get_authorized_health_profile:
                await endpoint(PATIENT, SimpleNamespace(), SimpleNamespace(), doctor)
            else:
                await endpoint(PATIENT, SimpleNamespace(), doctor)
        assert denied.value.status_code == 404
        assert denied.value.detail["code"] == "PATIENT_ACCESS_NOT_FOUND"

"""Local-account security auditing must only stage opaque, bounded facts."""

from __future__ import annotations

import pytest

from gerclaw_api.database.models import IdentitySecurityEvent
from gerclaw_api.repositories.account import SqlAlchemyAccountRepository


class _Session:
    def __init__(self) -> None:
        self.records: list[object] = []

    def add(self, record: object) -> None:
        self.records.append(record)


@pytest.mark.asyncio
async def test_identity_security_event_stores_only_an_opaque_subject() -> None:
    session = _Session()
    repository = SqlAlchemyAccountRepository(session)  # type: ignore[arg-type]
    fingerprint = "a" * 52

    await repository.record_security_event(
        tenant_id="tenant_public0001",
        subject_fingerprint=fingerprint,
        event_type="refresh",
        outcome="rejected",
    )

    assert len(session.records) == 1
    event = session.records[0]
    assert isinstance(event, IdentitySecurityEvent)
    assert event.subject_fingerprint == fingerprint
    assert event.actor_id is None
    assert event.event_type == "refresh"
    assert event.outcome == "rejected"
    assert not hasattr(event, "username")
    assert not hasattr(event, "password")
    assert not hasattr(event, "refresh_token")


@pytest.mark.asyncio
async def test_identity_security_event_rejects_nonopaque_subject() -> None:
    repository = SqlAlchemyAccountRepository(_Session())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="opaque fingerprint"):
        await repository.record_security_event(
            tenant_id="tenant_public0001",
            subject_fingerprint="patient@example.com",
            event_type="login",
            outcome="rejected",
        )

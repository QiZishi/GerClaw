"""Unit tests for deterministic, caller-owned risk-alert persistence semantics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.database.models import RiskAlert
from gerclaw_api.metrics import RISK_ALERTS
from gerclaw_api.modules.cga.models import CgaRiskRead
from gerclaw_api.modules.risk_alert.service import RiskAlertConflictError, RiskAlertService


class _Repository:
    def __init__(self) -> None:
        self.records: list[RiskAlert] = []

    async def get_by_source(
        self, *, tenant_id: str, actor_id: str, source_fingerprint: str
    ) -> RiskAlert | None:
        return next(
            (
                record
                for record in self.records
                if record.tenant_id == tenant_id
                and record.actor_id == actor_id
                and record.source_fingerprint == source_fingerprint
            ),
            None,
        )

    async def create(self, **kwargs: object) -> RiskAlert:
        now = datetime.now(UTC)
        record = RiskAlert(
            id=uuid.uuid4(),
            created_at=now,
            updated_at=now,
            status="active",
            revision=1,
            **kwargs,
        )
        self.records.append(record)
        return record

    async def list_for_owner(
        self, *, tenant_id: str, actor_id: str, status: str | None, limit: int
    ) -> list[RiskAlert]:
        return [
            record
            for record in self.records
            if record.tenant_id == tenant_id
            and record.actor_id == actor_id
            and (status is None or record.status == status)
        ][:limit]

    async def lock(self, *, alert_id: uuid.UUID, tenant_id: str, actor_id: str) -> RiskAlert:
        record = next(
            (
                item
                for item in self.records
                if item.id == alert_id and item.tenant_id == tenant_id and item.actor_id == actor_id
            ),
            None,
        )
        if record is None:
            raise LookupError("not found")
        return record


@pytest.mark.asyncio
async def test_immediate_cga_risk_is_deduplicated_and_does_not_expose_source_identifier() -> None:
    repository = _Repository()
    service = RiskAlertService(repository)  # type: ignore[arg-type]
    risk = CgaRiskRead(requires_immediate_safety_assessment=True, high_severity_follow_up=True)

    first = await service.sync_cga_risk(
        tenant_id="tenant_public0001",
        actor_id="usr_patient_alert0001",
        immediate_source_fingerprint="a" * 64,
        follow_up_source_fingerprint="b" * 64,
        risk=risk,
    )
    second = await service.sync_cga_risk(
        tenant_id="tenant_public0001",
        actor_id="usr_patient_alert0001",
        immediate_source_fingerprint="a" * 64,
        follow_up_source_fingerprint="b" * 64,
        risk=risk,
    )

    assert len(repository.records) == 1
    assert first[0].kind == "cga_immediate_safety"
    assert second[0].alert_id == first[0].alert_id
    assert "source_fingerprint" not in first[0].model_dump()
    assert "assessment" not in first[0].model_dump_json()


@pytest.mark.asyncio
async def test_high_follow_up_is_owner_scoped_and_acknowledgement_is_revision_fenced() -> None:
    repository = _Repository()
    service = RiskAlertService(repository)  # type: ignore[arg-type]
    created = await service.sync_cga_risk(
        tenant_id="tenant_public0001",
        actor_id="usr_patient_alert0001",
        immediate_source_fingerprint="a" * 64,
        follow_up_source_fingerprint="b" * 64,
        risk=CgaRiskRead(requires_immediate_safety_assessment=False, high_severity_follow_up=True),
    )
    alert = created[0]

    own = await service.list(
        tenant_id="tenant_public0001", actor_id="usr_patient_alert0001", status="active", limit=20
    )
    other = await service.list(
        tenant_id="tenant_public0001", actor_id="usr_patient_alert0002", status=None, limit=20
    )
    assert [item.alert_id for item in own.items] == [alert.alert_id]
    assert other.items == []

    acknowledged = await service.acknowledge(
        alert_id=alert.alert_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_alert0001",
        expected_revision=1,
        idempotency_key="idem_risk_alert_acknowledgement0001",
    )
    replayed = await service.acknowledge(
        alert_id=alert.alert_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_alert0001",
        expected_revision=1,
        idempotency_key="idem_risk_alert_acknowledgement0001",
    )
    assert acknowledged.status == "acknowledged"
    assert acknowledged.revision == 2
    assert acknowledged.acknowledged_at is not None
    assert replayed.revision == 2

    with pytest.raises(RiskAlertConflictError):
        await service.acknowledge(
            alert_id=alert.alert_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_alert0001",
            expected_revision=2,
            idempotency_key="idem_risk_alert_different_ack0001",
        )


@pytest.mark.asyncio
async def test_chat_red_flag_is_deduplicated_without_retaining_chat_content() -> None:
    repository = _Repository()
    service = RiskAlertService(repository)  # type: ignore[arg-type]

    first = await service.sync_chat_red_flag(
        tenant_id="tenant_public0001",
        actor_id="usr_patient_alert0001",
        source_fingerprint="c" * 64,
    )
    replayed = await service.sync_chat_red_flag(
        tenant_id="tenant_public0001",
        actor_id="usr_patient_alert0001",
        source_fingerprint="c" * 64,
    )

    assert first.kind == "chat_red_flag"
    assert first.severity == "critical"
    assert replayed.alert_id == first.alert_id
    assert len(repository.records) == 1
    assert repository.records[0].source == "chat"
    assert "source_fingerprint" not in first.model_dump()


@pytest.mark.asyncio
async def test_alert_metrics_are_bounded_and_track_lifecycle_without_identifiers() -> None:
    repository = _Repository()
    service = RiskAlertService(repository)  # type: ignore[arg-type]
    created_metric = RISK_ALERTS.labels(source="chat", severity="critical", outcome="created")
    deduplicated_metric = RISK_ALERTS.labels(
        source="chat", severity="critical", outcome="deduplicated"
    )
    acknowledged_metric = RISK_ALERTS.labels(
        source="chat", severity="critical", outcome="acknowledged"
    )
    before = (
        created_metric._value.get(),
        deduplicated_metric._value.get(),
        acknowledged_metric._value.get(),
    )

    alert = await service.sync_chat_red_flag(
        tenant_id="tenant_public0001",
        actor_id="usr_patient_alert0001",
        source_fingerprint="c" * 64,
    )
    await service.sync_chat_red_flag(
        tenant_id="tenant_public0001",
        actor_id="usr_patient_alert0001",
        source_fingerprint="c" * 64,
    )
    await service.acknowledge(
        alert_id=alert.alert_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_alert0001",
        expected_revision=1,
        idempotency_key="idem_risk_alert_metric0001",
    )

    assert created_metric._value.get() == before[0] + 1
    assert deduplicated_metric._value.get() == before[1] + 1
    assert acknowledged_metric._value.get() == before[2] + 1

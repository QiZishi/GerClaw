"""Unit tests for the non-clinical encrypted chronic-care ledger contract."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from gerclaw_api.database.models import ChronicCareCondition, ChronicCareMeasurement
from gerclaw_api.modules.chronic_care.models import (
    ChronicConditionCreateRequest,
    ChronicMeasurementCreateRequest,
)
from gerclaw_api.repositories.chronic_care import ChronicCareNotFoundError
from gerclaw_api.services.chronic_care_service import ChronicCareConflictError, ChronicCareService


class _Repository:
    def __init__(self) -> None:
        self.conditions: list[ChronicCareCondition] = []
        self.measurements: list[ChronicCareMeasurement] = []

    async def create_condition(self, **kwargs: object) -> ChronicCareCondition:
        now = datetime.now(UTC)
        record = ChronicCareCondition(
            id=uuid.uuid4(),
            created_at=now,
            updated_at=now,
            confirmation_status="self_reported",
            revision=1,
            **kwargs,
        )
        self.conditions.append(record)
        return record

    async def list_conditions(
        self, *, tenant_id: str, actor_id: str, limit: int
    ) -> list[ChronicCareCondition]:
        return [
            item
            for item in self.conditions
            if item.tenant_id == tenant_id and item.actor_id == actor_id
        ][:limit]

    async def get_condition(
        self, condition_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ChronicCareCondition:
        record = next(
            (
                item
                for item in self.conditions
                if item.id == condition_id
                and item.tenant_id == tenant_id
                and item.actor_id == actor_id
            ),
            None,
        )
        if record is None:
            raise ChronicCareNotFoundError(str(condition_id))
        return record

    async def create_measurement(self, **kwargs: object) -> ChronicCareMeasurement:
        await self.get_condition(
            kwargs["condition_id"], tenant_id=kwargs["tenant_id"], actor_id=kwargs["actor_id"]
        )
        record = ChronicCareMeasurement(
            id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            **kwargs,
        )
        self.measurements.append(record)
        return record

    async def list_measurements(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        condition_id: uuid.UUID,
        limit: int,
    ) -> list[ChronicCareMeasurement]:
        await self.get_condition(condition_id, tenant_id=tenant_id, actor_id=actor_id)
        return [
            item
            for item in self.measurements
            if item.tenant_id == tenant_id
            and item.actor_id == actor_id
            and item.condition_id == condition_id
        ][:limit]


@pytest.mark.asyncio
async def test_self_reported_measurements_are_owner_scoped_and_have_arithmetic_trends() -> None:
    repository = _Repository()
    service = ChronicCareService(repository)  # type: ignore[arg-type]
    condition = await service.create_condition(
        ChronicConditionCreateRequest(label="高血压"),
        tenant_id="tenant_public0001",
        actor_id="usr_patient_chronic0001",
    )
    first = await service.create_measurement(
        condition.condition_id,
        ChronicMeasurementCreateRequest(
            metric_label="收缩压", value=120, unit="mmHg", measured_at=datetime.now(UTC)
        ),
        tenant_id="tenant_public0001",
        actor_id="usr_patient_chronic0001",
    )
    second = await service.create_measurement(
        condition.condition_id,
        ChronicMeasurementCreateRequest(
            metric_label="收缩压",
            value=130,
            unit="mmHg",
            measured_at=datetime.now(UTC) + timedelta(seconds=1),
        ),
        tenant_id="tenant_public0001",
        actor_id="usr_patient_chronic0001",
    )

    assert condition.confirmation_status == "self_reported"
    assert first.value == 120
    assert second.value == 130
    trends = await service.trends(
        condition.condition_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_chronic0001",
    )
    assert trends.items[0].direction == "rising"
    assert trends.items[0].latest_value == 130
    assert trends.items[0].previous_value == 120
    assert "abnormal" not in trends.items[0].model_dump_json()

    own = await service.list_conditions(
        tenant_id="tenant_public0001", actor_id="usr_patient_chronic0001", limit=10
    )
    other = await service.list_conditions(
        tenant_id="tenant_public0001", actor_id="usr_patient_chronic0002", limit=10
    )
    assert [item.condition_id for item in own.items] == [condition.condition_id]
    assert other.items == []

    with pytest.raises(ChronicCareNotFoundError):
        await service.list_measurements(
            condition.condition_id,
            tenant_id="tenant_public0001",
            actor_id="usr_patient_chronic0002",
            limit=10,
        )


@pytest.mark.asyncio
async def test_measurement_rejects_materially_future_timestamp() -> None:
    repository = _Repository()
    service = ChronicCareService(repository)  # type: ignore[arg-type]
    condition = await service.create_condition(
        ChronicConditionCreateRequest(label="自述慢病"),
        tenant_id="tenant_public0001",
        actor_id="usr_patient_chronic0001",
    )

    with pytest.raises(ChronicCareConflictError):
        await service.create_measurement(
            condition.condition_id,
            ChronicMeasurementCreateRequest(
                metric_label="体重",
                value=60,
                unit="kg",
                measured_at=datetime.now(UTC) + timedelta(minutes=6),
            ),
            tenant_id="tenant_public0001",
            actor_id="usr_patient_chronic0001",
        )


@pytest.mark.asyncio
async def test_same_measurement_time_uses_append_order_for_non_clinical_trend() -> None:
    repository = _Repository()
    service = ChronicCareService(repository)  # type: ignore[arg-type]
    condition = await service.create_condition(
        ChronicConditionCreateRequest(label="自述慢病"),
        tenant_id="tenant_public0001",
        actor_id="usr_patient_chronic0001",
    )
    measured_at = datetime.now(UTC).replace(second=0, microsecond=0)
    await service.create_measurement(
        condition.condition_id,
        ChronicMeasurementCreateRequest(
            metric_label="自述指标", value=120, unit="单位", measured_at=measured_at
        ),
        tenant_id="tenant_public0001",
        actor_id="usr_patient_chronic0001",
    )
    await service.create_measurement(
        condition.condition_id,
        ChronicMeasurementCreateRequest(
            metric_label="自述指标", value=130, unit="单位", measured_at=measured_at
        ),
        tenant_id="tenant_public0001",
        actor_id="usr_patient_chronic0001",
    )

    trends = await service.trends(
        condition.condition_id,
        tenant_id="tenant_public0001",
        actor_id="usr_patient_chronic0001",
    )
    assert trends.items[0].direction == "rising"
    assert trends.items[0].latest_value == 130
    assert trends.items[0].previous_value == 120


def test_measurement_contract_rejects_non_finite_value() -> None:
    with pytest.raises(ValidationError):
        ChronicMeasurementCreateRequest(
            metric_label="体重", value=float("nan"), unit="kg", measured_at=datetime.now(UTC)
        )

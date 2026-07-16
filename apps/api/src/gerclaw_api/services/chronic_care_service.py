"""Non-clinical chronic-care ledger service with strict encrypted data projections."""

from __future__ import annotations

import unicodedata
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gerclaw_api.database.models import ChronicCareCondition, ChronicCareMeasurement
from gerclaw_api.modules.chronic_care.models import (
    ChronicConditionCreateRequest,
    ChronicConditionListRead,
    ChronicConditionRead,
    ChronicMeasurementCreateRequest,
    ChronicMeasurementListRead,
    ChronicMeasurementRead,
    ChronicTrendListRead,
    ChronicTrendRead,
)
from gerclaw_api.repositories.chronic_care import SqlAlchemyChronicCareRepository


class ChronicCareConflictError(RuntimeError):
    """An encrypted row cannot satisfy the versioned ledger contract."""


class _ConditionDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1, le=1)
    label: str = Field(min_length=1, max_length=80)


class _MeasurementDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1, le=1)
    metric_label: str = Field(min_length=1, max_length=80)
    value: float = Field(ge=0, le=10_000_000)
    unit: str = Field(min_length=1, max_length=32)
    measured_at: datetime


class ChronicCareService:
    """Persist user-entered facts without inferring clinical states or targets."""

    def __init__(self, repository: SqlAlchemyChronicCareRepository) -> None:
        self._repository = repository

    async def create_condition(
        self, payload: ChronicConditionCreateRequest, *, tenant_id: str, actor_id: str
    ) -> ChronicConditionRead:
        record = await self._repository.create_condition(
            tenant_id=tenant_id,
            actor_id=actor_id,
            details=_ConditionDetails(label=payload.label).model_dump(mode="json"),
        )
        return self._condition_read(record)

    async def list_conditions(
        self, *, tenant_id: str, actor_id: str, limit: int
    ) -> ChronicConditionListRead:
        records = await self._repository.list_conditions(
            tenant_id=tenant_id, actor_id=actor_id, limit=limit
        )
        return ChronicConditionListRead(items=[self._condition_read(record) for record in records])

    async def create_measurement(
        self,
        condition_id: uuid.UUID,
        payload: ChronicMeasurementCreateRequest,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> ChronicMeasurementRead:
        now = datetime.now(UTC)
        measured_at = payload.measured_at
        if measured_at.tzinfo is None:
            raise ChronicCareConflictError("measurement time must include a timezone")
        measured_at = measured_at.astimezone(UTC)
        if measured_at > now + timedelta(minutes=5):
            raise ChronicCareConflictError("measurement time cannot be materially in the future")
        record = await self._repository.create_measurement(
            tenant_id=tenant_id,
            actor_id=actor_id,
            condition_id=condition_id,
            details=_MeasurementDetails(
                metric_label=payload.metric_label,
                value=payload.value,
                unit=payload.unit,
                measured_at=measured_at,
            ).model_dump(mode="json"),
        )
        return self._measurement_read(record)

    async def list_measurements(
        self,
        condition_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int,
    ) -> ChronicMeasurementListRead:
        records = await self._repository.list_measurements(
            tenant_id=tenant_id,
            actor_id=actor_id,
            condition_id=condition_id,
            limit=limit,
        )
        items = sorted(
            (self._measurement_read(record) for record in records),
            key=lambda item: (item.measured_at, item.measurement_id),
            reverse=True,
        )
        return ChronicMeasurementListRead(items=items)

    async def trends(
        self, condition_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ChronicTrendListRead:
        records = await self._repository.list_measurements(
            tenant_id=tenant_id,
            actor_id=actor_id,
            condition_id=condition_id,
            limit=200,
        )
        grouped: dict[str, list[ChronicMeasurementRead]] = defaultdict(list)
        for record in records:
            item = self._measurement_read(record)
            grouped[self._metric_key(item.metric_label, item.unit)].append(item)
        trends: list[ChronicTrendRead] = []
        for items in grouped.values():
            ordered = sorted(
                items, key=lambda item: (item.measured_at, item.measurement_id), reverse=True
            )
            latest = ordered[0]
            previous = ordered[1] if len(ordered) > 1 else None
            direction = (
                "insufficient_data"
                if previous is None
                else "rising"
                if latest.value > previous.value
                else "falling"
                if latest.value < previous.value
                else "unchanged"
            )
            trends.append(
                ChronicTrendRead(
                    metric_label=latest.metric_label,
                    unit=latest.unit,
                    direction=direction,
                    latest_measurement_id=latest.measurement_id,
                    latest_value=latest.value,
                    latest_measured_at=latest.measured_at,
                    previous_measurement_id=(
                        previous.measurement_id if previous is not None else None
                    ),
                    previous_value=previous.value if previous is not None else None,
                    previous_measured_at=previous.measured_at if previous is not None else None,
                )
            )
        return ChronicTrendListRead(
            items=sorted(
                trends,
                key=lambda item: (item.latest_measured_at, item.metric_label),
                reverse=True,
            )
        )

    @staticmethod
    def _metric_key(label: str, unit: str) -> str:
        normalized_label = unicodedata.normalize("NFKC", label).strip().casefold()
        normalized_unit = unit.strip().casefold()
        return f"{normalized_label}\x00{normalized_unit}"

    @staticmethod
    def _condition_read(record: ChronicCareCondition) -> ChronicConditionRead:
        try:
            details = _ConditionDetails.model_validate(record.details)
        except ValidationError as error:
            raise ChronicCareConflictError("stored chronic-care condition is invalid") from error
        return ChronicConditionRead(
            condition_id=record.id,
            label=details.label,
            confirmation_status=record.confirmation_status,
            revision=record.revision,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _measurement_read(record: ChronicCareMeasurement) -> ChronicMeasurementRead:
        try:
            details = _MeasurementDetails.model_validate(record.details)
        except ValidationError as error:
            raise ChronicCareConflictError("stored chronic-care measurement is invalid") from error
        return ChronicMeasurementRead(
            measurement_id=record.id,
            condition_id=record.condition_id,
            metric_label=details.metric_label,
            value=details.value,
            unit=details.unit,
            measured_at=details.measured_at,
            created_at=record.created_at,
        )

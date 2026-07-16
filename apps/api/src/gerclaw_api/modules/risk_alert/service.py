"""Policy-owned alert creation and owner acknowledgement semantics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from gerclaw_api.database.models import RiskAlert
from gerclaw_api.metrics import RISK_ALERTS
from gerclaw_api.modules.cga.models import CgaRiskRead
from gerclaw_api.modules.risk_alert.models import (
    RISK_ALERT_POLICY_VERSION,
    RiskAlertDetails,
    RiskAlertListRead,
    RiskAlertRead,
)


class RiskAlertConflictError(RuntimeError):
    """A caller attempted a stale or mismatched acknowledgement."""


class RiskAlertNotFoundError(RuntimeError):
    """The caller cannot observe the requested alert."""


class RiskAlertRepository(Protocol):
    async def get_by_source(
        self, *, tenant_id: str, actor_id: str, source_fingerprint: str
    ) -> RiskAlert | None: ...

    async def create(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        source: str,
        source_fingerprint: str,
        policy_version: str,
        details: dict[str, object],
    ) -> RiskAlert: ...

    async def list_for_owner(
        self, *, tenant_id: str, actor_id: str, status: str | None, limit: int
    ) -> list[RiskAlert]: ...

    async def lock(self, *, alert_id: uuid.UUID, tenant_id: str, actor_id: str) -> RiskAlert: ...


_IMMEDIATE_DETAILS = RiskAlertDetails(
    kind="cga_immediate_safety",
    severity="critical",
    title="需要立即安全评估",
    message="本次筛查提示需要立即进行安全评估。",
    action="请立即联系家人、医生或当地紧急医疗服务; 如有紧急危险, 请立即拨打当地急救电话。",
)
_FOLLOW_UP_DETAILS = RiskAlertDetails(
    kind="cga_high_follow_up",
    severity="high",
    title="建议尽快临床随访",
    message="本次筛查提示需要尽快进行临床随访。",
    action="请尽快联系医生, 结合完整病史和专业评估确定下一步处理。",
)
_CHAT_RED_FLAG_DETAILS = RiskAlertDetails(
    kind="chat_red_flag",
    severity="critical",
    title="需要立即就医",
    message="本次对话提示可能存在紧急健康风险。",
    action="请立即联系家人、医生或当地紧急医疗服务; 如有紧急危险, 请立即拨打当地急救电话。",
)


class RiskAlertService:
    """Create only server-derived CGA alerts and acknowledge them safely."""

    def __init__(self, repository: RiskAlertRepository) -> None:
        self._repository = repository

    async def sync_cga_risk(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        immediate_source_fingerprint: str,
        follow_up_source_fingerprint: str,
        risk: CgaRiskRead,
    ) -> tuple[RiskAlertRead, ...]:
        """Idempotently persist currently asserted deterministic CGA signals."""

        created: list[RiskAlertRead] = []
        if risk.requires_immediate_safety_assessment:
            created.append(
                await self._ensure(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    source="cga",
                    source_fingerprint=immediate_source_fingerprint,
                    details=_IMMEDIATE_DETAILS,
                )
            )
        elif risk.high_severity_follow_up:
            created.append(
                await self._ensure(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    source="cga",
                    source_fingerprint=follow_up_source_fingerprint,
                    details=_FOLLOW_UP_DETAILS,
                )
            )
        return tuple(created)

    async def sync_chat_red_flag(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        source_fingerprint: str,
    ) -> RiskAlertRead:
        """Persist one emergency short-circuit without retaining chat content or codes."""

        return await self._ensure(
            tenant_id=tenant_id,
            actor_id=actor_id,
            source="chat",
            source_fingerprint=source_fingerprint,
            details=_CHAT_RED_FLAG_DETAILS,
        )

    async def list(
        self, *, tenant_id: str, actor_id: str, status: str | None, limit: int
    ) -> RiskAlertListRead:
        records = await self._repository.list_for_owner(
            tenant_id=tenant_id, actor_id=actor_id, status=status, limit=limit
        )
        return RiskAlertListRead(items=[self._read(record) for record in records])

    async def acknowledge(
        self,
        *,
        alert_id: uuid.UUID,
        tenant_id: str,
        actor_id: str,
        expected_revision: int,
        idempotency_key: str,
    ) -> RiskAlertRead:
        record = await self._repository.lock(
            alert_id=alert_id, tenant_id=tenant_id, actor_id=actor_id
        )
        if record.status == "acknowledged":
            if record.acknowledgement_idempotency_key != idempotency_key:
                raise RiskAlertConflictError("risk alert has already been acknowledged")
            self._record_metric(record, outcome="acknowledgement_replayed")
            return self._read(record)
        if record.revision != expected_revision:
            raise RiskAlertConflictError("risk alert has changed; refresh before acknowledging")
        acknowledged_at = datetime.now(UTC)
        record.status = "acknowledged"
        record.acknowledgement_idempotency_key = idempotency_key
        record.acknowledged_at = acknowledged_at
        record.updated_at = acknowledged_at
        record.revision += 1
        self._record_metric(record, outcome="acknowledged")
        return self._read(record)

    async def _ensure(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        source: str,
        source_fingerprint: str,
        details: RiskAlertDetails,
    ) -> RiskAlertRead:
        existing = await self._repository.get_by_source(
            tenant_id=tenant_id, actor_id=actor_id, source_fingerprint=source_fingerprint
        )
        if existing is None:
            existing = await self._repository.create(
                tenant_id=tenant_id,
                actor_id=actor_id,
                source=source,
                source_fingerprint=source_fingerprint,
                policy_version=RISK_ALERT_POLICY_VERSION,
                details=details.model_dump(mode="json"),
            )
            RISK_ALERTS.labels(source=source, severity=details.severity, outcome="created").inc()
        else:
            self._record_metric(existing, outcome="deduplicated")
        return self._read(existing)

    @staticmethod
    def _record_metric(record: RiskAlert, *, outcome: str) -> None:
        """Count only bounded operational state, never owner or alert content."""

        try:
            details = RiskAlertDetails.model_validate(record.details)
        except ValueError:
            return
        if record.source not in {"cga", "chat"}:
            return
        RISK_ALERTS.labels(source=record.source, severity=details.severity, outcome=outcome).inc()

    @staticmethod
    def _read(record: RiskAlert) -> RiskAlertRead:
        try:
            details = RiskAlertDetails.model_validate(record.details)
        except ValueError as error:
            raise RiskAlertConflictError("stored risk alert is invalid") from error
        return RiskAlertRead(
            alert_id=record.id,
            kind=details.kind,
            severity=details.severity,
            title=details.title,
            message=details.message,
            action=details.action,
            status=record.status,
            revision=record.revision,
            policy_version=record.policy_version,
            created_at=record.created_at,
            updated_at=record.updated_at,
            acknowledged_at=record.acknowledged_at,
        )

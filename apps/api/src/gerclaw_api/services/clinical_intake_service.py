"""Server-owned state transitions for non-clinical workflow intake."""
# ruff: noqa: RUF001

from __future__ import annotations

import uuid
from typing import Literal, cast

from gerclaw_api.database.models import ClinicalIntake
from gerclaw_api.modules.prescription.intake import (
    ClinicalIntakeKind,
    intake_definition,
)
from gerclaw_api.modules.prescription.models import (
    ClinicalIntakeFieldRead,
    ClinicalIntakeRead,
)
from gerclaw_api.repositories.clinical_intake import SqlAlchemyClinicalIntakeRepository

GOVERNANCE_NOTICE = (
    "当前仅完成信息收集。医学规则、医生审核和患者授权尚未启用，"
    "系统不会生成处方、用药调整或诊断结论。"
)


class ClinicalIntakeConflictError(RuntimeError):
    """The requested transition violates the server-owned intake contract."""


class ClinicalIntakeService:
    def __init__(self, repository: SqlAlchemyClinicalIntakeRepository) -> None:
        self._repository = repository

    async def start(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
        kind: ClinicalIntakeKind,
    ) -> ClinicalIntakeRead:
        definition = intake_definition(kind)
        record = await self._repository.find_by_session_kind(
            tenant_id=tenant_id,
            actor_id=actor_id,
            session_id=session_id,
            kind=kind,
        )
        if record is None:
            record = await self._repository.create(
                tenant_id=tenant_id,
                actor_id=actor_id,
                session_id=session_id,
                kind=kind,
                definition_version=definition.version,
            )
        return self._read(record)

    async def get(
        self, intake_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ClinicalIntakeRead:
        return self._read(
            await self._repository.get(intake_id, tenant_id=tenant_id, actor_id=actor_id)
        )

    async def update(
        self,
        intake_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        expected_revision: int,
        answers: dict[str, str],
    ) -> ClinicalIntakeRead:
        record = await self._repository.lock(intake_id, tenant_id=tenant_id, actor_id=actor_id)
        definition = intake_definition(cast(ClinicalIntakeKind, record.kind))
        previous = self._answers(record)
        normalized = self._validated_answers(definition.kind, answers)
        candidate = {**previous, **normalized}
        if candidate == previous:
            return self._read(record)
        if record.revision != expected_revision:
            raise ClinicalIntakeConflictError("intake has changed; refresh before updating")
        record.answers = candidate
        record.status = (
            "information_complete_pending_governance"
            if all(
                candidate.get(field.id, "").strip()
                for field in definition.fields
                if field.required
            )
            else "collecting"
        )
        record.revision += 1
        return self._read(record)

    @staticmethod
    def _answers(record: ClinicalIntake) -> dict[str, str]:
        raw = record.answers
        if not isinstance(raw, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in raw.items()
        ):
            raise ClinicalIntakeConflictError("persisted intake answers are invalid")
        return dict(raw)

    @staticmethod
    def _validated_answers(kind: ClinicalIntakeKind, answers: dict[str, str]) -> dict[str, str]:
        definition = intake_definition(kind)
        fields = {field.id: field for field in definition.fields}
        normalized: dict[str, str] = {}
        for field_id, value in answers.items():
            field = fields.get(field_id)
            if field is None:
                raise ClinicalIntakeConflictError("answer field is not declared by this intake")
            value = value.strip()
            if len(value) > field.max_length:
                raise ClinicalIntakeConflictError("answer exceeds the server-defined length limit")
            normalized[field_id] = value
        return normalized

    @classmethod
    def _read(cls, record: ClinicalIntake) -> ClinicalIntakeRead:
        definition = intake_definition(cast(ClinicalIntakeKind, record.kind))
        answers = cls._answers(record)
        missing = [
            field.id
            for field in definition.fields
            if field.required and not answers.get(field.id, "").strip()
        ]
        expected_status: Literal["collecting", "information_complete_pending_governance"] = (
            "collecting" if missing else "information_complete_pending_governance"
        )
        if record.status != expected_status:
            raise ClinicalIntakeConflictError("persisted intake status is invalid")
        return ClinicalIntakeRead(
            intake_id=record.id,
            session_id=record.session_id,
            kind=definition.kind,
            definition_version=record.definition_version,
            status=expected_status,
            revision=record.revision,
            title=definition.title,
            description=definition.description,
            fields=[ClinicalIntakeFieldRead(**field.__dict__) for field in definition.fields],
            answers=answers,
            missing_required_fields=missing,
            governance_notice=GOVERNANCE_NOTICE,
            updated_at=record.updated_at,
        )

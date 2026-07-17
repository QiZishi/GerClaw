"""Server-owned state transitions for non-clinical workflow intake."""
# ruff: noqa: RUF001

from __future__ import annotations

import uuid
from typing import Literal, cast

from gerclaw_api.database.models import ClinicalIntake
from gerclaw_api.modules.document.models import UploadedDocumentContext
from gerclaw_api.modules.document.service import DocumentContextError, DocumentService
from gerclaw_api.modules.input_output.clinical_intake import (
    ClinicalIntakeDefinition,
    ClinicalIntakeKind,
)
from gerclaw_api.modules.medication_review.intake import MEDICATION_REVIEW_INTAKE_DEFINITION
from gerclaw_api.modules.prescription.intake import PRESCRIPTION_INTAKE_DEFINITION
from gerclaw_api.modules.prescription.models import (
    ClinicalIntakeFieldRead,
    ClinicalIntakeRead,
    PreparedPrescriptionInput,
    PrescriptionInputReadiness,
)
from gerclaw_api.repositories.clinical_intake import SqlAlchemyClinicalIntakeRepository

PRESCRIPTION_GOVERNANCE_NOTICE = (
    "信息完整后可生成带本地医学证据的五大处方待临床复核草案；它不是正式处方或诊断。"
    "DDI、Beers 和剂量规则尚未配置，任何药物调整必须由医生或药师核对。"
)
MEDICATION_REVIEW_GOVERNANCE_NOTICE = (
    "可生成来源可追溯的有限规则审查结果，供医生或药师复核；它不是正式处方或诊断。"
    "Beers 规则尚未安装，有限规则未命中不代表用药安全，任何药物调整必须由医生或药师核对。"
)
INTAKE_DEFINITIONS: dict[ClinicalIntakeKind, ClinicalIntakeDefinition] = {
    "prescription": PRESCRIPTION_INTAKE_DEFINITION,
    "medication_review": MEDICATION_REVIEW_INTAKE_DEFINITION,
}


class ClinicalIntakeConflictError(RuntimeError):
    """The requested transition violates the server-owned intake contract."""


def intake_definition(kind: ClinicalIntakeKind) -> ClinicalIntakeDefinition:
    """Resolve the one server-owned definition for a bounded intake kind."""

    return INTAKE_DEFINITIONS[kind]


def governance_notice(kind: ClinicalIntakeKind) -> str:
    """Keep the owner-visible notice aligned with the actual workflow boundary."""

    return (
        PRESCRIPTION_GOVERNANCE_NOTICE
        if kind == "prescription"
        else MEDICATION_REVIEW_GOVERNANCE_NOTICE
    )


class ClinicalIntakeService:
    def __init__(
        self,
        repository: SqlAlchemyClinicalIntakeRepository,
        document_service: DocumentService | None = None,
    ) -> None:
        self._repository = repository
        self._document_service = document_service

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
        document_ids: list[uuid.UUID] | None = None,
    ) -> ClinicalIntakeRead:
        record = await self._repository.lock(intake_id, tenant_id=tenant_id, actor_id=actor_id)
        definition = intake_definition(cast(ClinicalIntakeKind, record.kind))
        previous = self._answers(record)
        previous_document_ids = self._document_ids(record)
        normalized = self._validated_answers(definition.kind, answers)
        candidate = {**previous, **normalized}
        candidate_document_ids = (
            previous_document_ids
            if document_ids is None
            else self._validated_document_ids(document_ids)
        )
        if document_ids is not None:
            if definition.kind != "prescription" and candidate_document_ids:
                raise ClinicalIntakeConflictError(
                    "uploaded documents are only supported for prescription intake"
                )
            await self._validate_document_ownership(
                candidate_document_ids,
                tenant_id=tenant_id,
                actor_id=actor_id,
                session_id=record.session_id,
            )
        if candidate == previous and candidate_document_ids == previous_document_ids:
            return self._read(record)
        if record.revision != expected_revision:
            raise ClinicalIntakeConflictError("intake has changed; refresh before updating")
        record.answers = candidate
        record.document_ids = candidate_document_ids
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

    async def prepare_prescription_input(
        self, intake_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> PreparedPrescriptionInput:
        """Resolve complete, owner-scoped materials for a future governed workflow.

        It performs no RAG, model, rule-engine, diagnosis, or prescription
        action. Document bodies are only resolved after the intake is complete
        and cannot be silently truncated: a future clinician-facing workflow
        must either receive all selected material or fail safely.
        """

        intake = await self.get(intake_id, tenant_id=tenant_id, actor_id=actor_id)
        if intake.kind != "prescription":
            raise ClinicalIntakeConflictError("prescription input is unavailable for this intake")
        if intake.status != "information_complete_pending_governance":
            raise ClinicalIntakeConflictError("prescription information is incomplete")

        documents: list[UploadedDocumentContext] = []
        if intake.document_ids:
            if self._document_service is None:
                raise ClinicalIntakeConflictError("uploaded document resolution is unavailable")
            try:
                documents = await self._document_service.resolve_context(
                    intake.document_ids,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    session_id=intake.session_id,
                    max_characters=self._document_service.context_max_characters,
                    allow_truncation=False,
                )
            except DocumentContextError as error:
                raise ClinicalIntakeConflictError(
                    "uploaded prescription input is no longer complete"
                ) from error
        return PreparedPrescriptionInput(
            intake_id=intake.intake_id,
            session_id=intake.session_id,
            definition_version=intake.definition_version,
            answers=intake.answers,
            uploaded_documents=tuple(documents),
        )

    async def prescription_input_readiness(
        self, intake_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> PrescriptionInputReadiness:
        """Validate private preparation and project only safe owner-visible counts."""

        prepared = await self.prepare_prescription_input(
            intake_id, tenant_id=tenant_id, actor_id=actor_id
        )
        return PrescriptionInputReadiness(
            intake_id=prepared.intake_id,
            definition_version=prepared.definition_version,
            answer_field_count=len(prepared.answers),
            uploaded_document_count=len(prepared.uploaded_documents),
            governance_notice=PRESCRIPTION_GOVERNANCE_NOTICE,
        )

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
    def _document_ids(record: ClinicalIntake) -> list[str]:
        raw = record.document_ids
        if raw is None:
            return []
        if (
            not isinstance(raw, list)
            or len(raw) > 5
            or any(not isinstance(item, str) for item in raw)
        ):
            raise ClinicalIntakeConflictError("persisted intake document references are invalid")
        try:
            normalized = [str(uuid.UUID(item)) for item in raw]
        except (TypeError, ValueError, AttributeError) as error:
            raise ClinicalIntakeConflictError(
                "persisted intake document references are invalid"
            ) from error
        if len(set(normalized)) != len(normalized):
            raise ClinicalIntakeConflictError("persisted intake document references are invalid")
        return normalized

    @staticmethod
    def _validated_document_ids(document_ids: list[uuid.UUID]) -> list[str]:
        normalized = [str(item) for item in document_ids]
        if len(normalized) > 5:
            raise ClinicalIntakeConflictError("too many uploaded document references")
        if len(set(normalized)) != len(normalized):
            raise ClinicalIntakeConflictError("duplicate uploaded document reference")
        return normalized

    async def _validate_document_ownership(
        self,
        document_ids: list[str],
        *,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
    ) -> None:
        if not document_ids:
            return
        if self._document_service is None:
            raise ClinicalIntakeConflictError("uploaded document validation is unavailable")
        try:
            for document_id in document_ids:
                await self._document_service.get(
                    uuid.UUID(document_id),
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    session_id=session_id,
                )
        except (DocumentContextError, ValueError, RuntimeError) as error:
            raise ClinicalIntakeConflictError(
                "uploaded document is not active in this session"
            ) from error

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
        if record.definition_version != definition.version:
            raise ClinicalIntakeConflictError("persisted intake definition is unsupported")
        answers = cls._answers(record)
        document_ids = cls._document_ids(record)
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
            document_ids=[uuid.UUID(item) for item in document_ids],
            missing_required_fields=missing,
            governance_notice=governance_notice(definition.kind),
            updated_at=record.updated_at,
        )

"""Authenticated intake and evidence-bound draft endpoints for governed workflows."""

from __future__ import annotations

import asyncio
import json
import uuid
from time import monotonic
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import (
    AuthContext,
    require_clinical_intake_read,
    require_clinical_intake_write,
)
from gerclaw_api.dependencies import get_database_session, get_trace_service
from gerclaw_api.domain.enums import TraceEventStatus, TraceEventType, TraceStatus
from gerclaw_api.domain.trace_schemas import (
    TRACE_ID_PATTERN,
    TraceEventCreate,
    TraceFinishRequest,
    TraceStartRequest,
    bounded_trace_duration_ms,
)
from gerclaw_api.middleware import set_active_trace
from gerclaw_api.modules.agent_harness.safety import EvidenceUnavailableError
from gerclaw_api.modules.document.service import DocumentService
from gerclaw_api.modules.input_output.clinical_intake import ClinicalIntakeKind
from gerclaw_api.modules.medication_review.models import (
    MedicationReconciliationRead,
    MedicationReviewDraft,
    MedicationReviewDraftHistoryRead,
    MedicationReviewDraftRead,
    MedicationReviewRequest,
)
from gerclaw_api.modules.medication_review.reconciliation import (
    MedicationReconciliationInputError,
    reconcile_medication_list,
)
from gerclaw_api.modules.medication_review.rules_engine import (
    MedicationRulesInputError,
    review_medication_list,
)
from gerclaw_api.modules.prescription.generator import (
    EvidenceBoundPrescriptionGenerator,
    PrescriptionGenerationError,
    PrescriptionRedFlagError,
    StructuredPrescriptionModel,
)
from gerclaw_api.modules.prescription.intake_extractor import (
    PrescriptionIntakeExtractionError,
    PrescriptionIntakeExtractor,
    StructuredIntakeModel,
)
from gerclaw_api.modules.prescription.models import (
    ClinicalIntakeRead,
    ClinicalIntakeStartRequest,
    ClinicalIntakeUpdateRequest,
    FivePrescriptionDraft,
    PrescriptionConversationTurnRead,
    PrescriptionConversationTurnRequest,
    PrescriptionDraftHistoryRead,
    PrescriptionDraftRead,
    PrescriptionDraftReviewRead,
    PrescriptionGenerationCancelRead,
    PrescriptionInputReadiness,
)
from gerclaw_api.modules.risk_alert.service import RiskAlertService
from gerclaw_api.modules.workflows import (
    WorkflowContextError,
    WorkflowId,
    get_default_workflow_registry,
)
from gerclaw_api.repositories.clinical_intake import (
    ClinicalIntakeNotFoundError,
    SqlAlchemyClinicalIntakeRepository,
)
from gerclaw_api.repositories.conversation import SqlAlchemyConversationRepository
from gerclaw_api.repositories.document import SqlAlchemyDocumentRepository
from gerclaw_api.repositories.medication_review_draft import (
    SqlAlchemyMedicationReviewDraftRepository,
)
from gerclaw_api.repositories.prescription_draft import SqlAlchemyPrescriptionDraftRepository
from gerclaw_api.repositories.risk_alert import SqlAlchemyRiskAlertRepository
from gerclaw_api.security import audit_hmac_digest
from gerclaw_api.services.chat_cancellation import (
    ChatCancellationRegistry,
    ChatCancellationUnavailable,
)
from gerclaw_api.services.clinical_intake_service import (
    ClinicalIntakeConflictError,
    ClinicalIntakeService,
    intake_definition,
)
from gerclaw_api.services.conversation_service import ConversationNotFoundError, ConversationService
from gerclaw_api.services.model_egress_audit import SqlAlchemyModelPromptEgressAudit
from gerclaw_api.services.model_router import (
    ModelAttempt,
    bind_model_prompt_egress_audit,
    capture_model_attempts,
)
from gerclaw_api.services.rate_limit import RateLimiter
from gerclaw_api.services.trace_service import TraceConflictError, TraceService

router = APIRouter(prefix="/clinical-intakes", tags=["clinical-intakes"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
ReadIdentity = Annotated[AuthContext, Depends(require_clinical_intake_read)]
WriteIdentity = Annotated[AuthContext, Depends(require_clinical_intake_write)]
TraceIdPath = Annotated[str, Path(pattern=TRACE_ID_PATTERN)]


async def _enforce_rate_limit(request: Request, identity: AuthContext) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)


async def _require_session(
    session: AsyncSession, session_id: uuid.UUID, identity: AuthContext
) -> None:
    try:
        await ConversationService(SqlAlchemyConversationRepository(session)).require_session(
            session_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CHAT_SESSION_NOT_FOUND", "message": "session not found"},
        ) from error


def _service(session: AsyncSession, request: Request) -> ClinicalIntakeService:
    return ClinicalIntakeService(
        SqlAlchemyClinicalIntakeRepository(session),
        DocumentService(SqlAlchemyDocumentRepository(session), request.app.state.settings),
    )


def _trace_service(request: Request, session: SessionDependency) -> TraceService:
    return get_trace_service(
        session, max_events_per_trace=request.app.state.settings.max_events_per_trace
    )


TraceServiceDependency = Annotated[TraceService, Depends(_trace_service)]


def _module_name(kind: ClinicalIntakeKind) -> str:
    """Return the audited domain owner for one server-defined intake type."""

    return "prescription" if kind == "prescription" else "medication_review"


def _request_fingerprint(
    request: Request,
    payload: (
        ClinicalIntakeStartRequest
        | ClinicalIntakeUpdateRequest
        | PrescriptionConversationTurnRequest
    ),
) -> str:
    """Bind retries without exposing encrypted clinical input in audit storage."""

    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return audit_hmac_digest(
        request.app.state.settings.auth_jwt_secret.get_secret_value().encode(),
        canonical.encode(),
    )


def _medication_alert_fingerprints(
    request: Request,
    *,
    intake_id: uuid.UUID,
    result: MedicationReviewDraft,
) -> dict[str, str]:
    """Deduplicate severe rule hits without storing drug details in alert rows."""

    secret = request.app.state.settings.auth_jwt_secret.get_secret_value().encode()
    return {
        finding.finding_id: audit_hmac_digest(
            secret,
            (
                f"risk-alert:v2:medication_review:{intake_id}:"
                f"{result.ruleset_version}:{finding.finding_id}"
            ).encode(),
        )
        for finding in result.findings
        if finding.severity in {"contraindicated", "major"}
    }


async def _start_write_trace(
    *,
    request: Request,
    traces: TraceService,
    identity: AuthContext,
    session_id: uuid.UUID,
    kind: ClinicalIntakeKind,
    operation: str,
    payload: (
        ClinicalIntakeStartRequest
        | ClinicalIntakeUpdateRequest
        | PrescriptionConversationTurnRequest
    ),
) -> tuple[str, float]:
    trace_id = str(request.state.trace_id)
    set_active_trace(request.scope, trace_id)
    started = monotonic()
    result = await traces.start_trace_with_status(
        TraceStartRequest(
            session_id=session_id,
            execution_type="clinical.intake",
            attributes={
                "feature": kind,
                "module": _module_name(kind),
                "operation": operation,
                "request_fingerprint": _request_fingerprint(request, payload),
                "version": "clinical-intake-v1",
            },
        ),
        str(request.state.request_id),
        trace_id=trace_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        commit=False,
    )
    if not result.created:
        raise TraceConflictError("clinical intake trace is already in use")
    return trace_id, started


async def _finish_write_trace(
    *,
    traces: TraceService,
    tenant_id: str,
    trace_id: str,
    operation: str,
    elapsed_started_at: float,
    result: ClinicalIntakeRead,
) -> None:
    trace_suffix = trace_id.removeprefix("trace_")
    await traces.append_event(
        tenant_id,
        trace_id,
        TraceEventCreate(
            event_id=f"event_{trace_suffix}_{operation}",
            event_type=TraceEventType.CLINICAL_INTAKE,
            status=TraceEventStatus.SUCCEEDED,
            payload={
                "feature": result.kind,
                "operation": operation,
                "version": result.definition_version,
                "event_count": len(result.answers),
                "document_count": len(result.document_ids),
                "outcome": result.status,
                "success": True,
            },
            duration_ms=bounded_trace_duration_ms(monotonic() - elapsed_started_at),
        ),
        commit=False,
    )
    await traces.finish_trace(
        tenant_id,
        trace_id,
        TraceFinishRequest(
            idempotency_key=f"finish_{trace_suffix}_{operation}",
            status=TraceStatus.COMPLETED,
            attributes={
                "feature": result.kind,
                "module": _module_name(result.kind),
                "operation": operation,
                "result_code": result.status,
                "version": result.definition_version,
            },
        ),
        commit=False,
    )


async def _append_model_attempt_events(
    *,
    traces: TraceService,
    tenant_id: str,
    trace_id: str,
    attempts: list[ModelAttempt],
) -> None:
    """Persist slot-only model outcomes without retaining prompts or responses."""

    trace_suffix = trace_id.removeprefix("trace_")
    for index, attempt in enumerate(attempts):
        await traces.append_event(
            tenant_id,
            trace_id,
            TraceEventCreate(
                event_id=f"event_{trace_suffix}_model_{index}",
                event_type=TraceEventType.MODEL_CALL,
                status=(
                    TraceEventStatus.SUCCEEDED
                    if attempt.outcome == "succeeded"
                    else TraceEventStatus.STARTED
                    if attempt.outcome == "started"
                    else TraceEventStatus.FAILED
                ),
                payload={
                    "model": f"slot_{attempt.preference}",
                    **(
                        {"capability_version": attempt.capability_version}
                        if attempt.capability_version
                        else {}
                    ),
                    "outcome": attempt.outcome,
                    "success": attempt.outcome == "succeeded",
                    **({"error_code": attempt.error_code.casefold()} if attempt.error_code else {}),
                },
            ),
            commit=False,
        )


async def _finish_conversation_failure_trace(
    *,
    traces: TraceService,
    tenant_id: str,
    trace_id: str | None,
    started_at: float | None,
    attempts: list[ModelAttempt],
) -> None:
    if trace_id is None or started_at is None:
        return
    await _append_model_attempt_events(
        traces=traces, tenant_id=tenant_id, trace_id=trace_id, attempts=attempts
    )
    trace_suffix = trace_id.removeprefix("trace_")
    await traces.append_event(
        tenant_id,
        trace_id,
        TraceEventCreate(
            event_id=f"event_{trace_suffix}_conversation_failed",
            event_type=TraceEventType.SYSTEM_ERROR,
            status=TraceEventStatus.FAILED,
            payload={
                "module": "prescription",
                "operation": "conversation_turn",
                "error_code": "prescription_intake_unavailable",
            },
            duration_ms=bounded_trace_duration_ms(monotonic() - started_at),
        ),
        commit=False,
    )
    await traces.finish_trace(
        tenant_id,
        trace_id,
        TraceFinishRequest(
            idempotency_key=f"finish_{trace_suffix}_conversation_turn",
            status=TraceStatus.FAILED,
            error_code="prescription_intake_unavailable",
            error_summary="prescription intake extraction did not complete",
            attributes={
                "module": "prescription",
                "operation": "conversation_turn",
                "success": False,
            },
        ),
        commit=False,
    )


def _prescription_error_code(error: Exception) -> str:
    """Map generation failures to a stable, non-clinical public/audit code."""

    if isinstance(error, PrescriptionRedFlagError):
        return "PRESCRIPTION_EMERGENCY_BLOCKED"
    if isinstance(error, EvidenceUnavailableError):
        return "PRESCRIPTION_EVIDENCE_UNAVAILABLE"
    if isinstance(error, (ClinicalIntakeNotFoundError, ClinicalIntakeConflictError)):
        return "PRESCRIPTION_INPUT_NOT_READY"
    if isinstance(error, TraceConflictError):
        return "PRESCRIPTION_TRACE_CONFLICT"
    return "PRESCRIPTION_DRAFT_UNAVAILABLE"


async def _finish_prescription_failure_trace(
    *,
    traces: TraceService,
    tenant_id: str,
    trace_id: str | None,
    started_at: float | None,
    attempts: list[ModelAttempt],
    error_code: str,
) -> None:
    """Finish a started prescription trace without retaining provider error text.

    A provider/model failure used to return the correct 503 but leave a running
    Trace forever.  Slot-only attempt records make operational failures
    diagnosable without storing provider responses, prompts, or patient data.
    """

    if trace_id is None or started_at is None:
        return
    trace_suffix = trace_id.removeprefix("trace_")
    for index, attempt in enumerate(attempts):
        await traces.append_event(
            tenant_id,
            trace_id,
            TraceEventCreate(
                event_id=f"event_{trace_suffix}_model_{index}",
                event_type=TraceEventType.MODEL_CALL,
                status=(
                    TraceEventStatus.SUCCEEDED
                    if attempt.outcome == "succeeded"
                    else TraceEventStatus.STARTED
                    if attempt.outcome == "started"
                    else TraceEventStatus.FAILED
                ),
                payload={
                    "model": f"slot_{attempt.preference}",
                    **(
                        {"capability_version": attempt.capability_version}
                        if attempt.capability_version
                        else {}
                    ),
                    "outcome": attempt.outcome,
                    "success": attempt.outcome == "succeeded",
                    **({"error_code": attempt.error_code.casefold()} if attempt.error_code else {}),
                },
            ),
            commit=False,
        )
    await traces.append_event(
        tenant_id,
        trace_id,
        TraceEventCreate(
            event_id=f"event_{trace_suffix}_generate_draft_failed",
            event_type=TraceEventType.SYSTEM_ERROR,
            status=TraceEventStatus.FAILED,
            payload={
                "error_code": error_code.casefold(),
                "module": "prescription",
                "operation": "generate_draft",
                "result_code": error_code.casefold(),
            },
            duration_ms=bounded_trace_duration_ms(monotonic() - started_at),
        ),
        commit=False,
    )
    await traces.finish_trace(
        tenant_id,
        trace_id,
        TraceFinishRequest(
            idempotency_key=f"finish_{trace_suffix}",
            status=TraceStatus.FAILED,
            error_code=error_code.casefold(),
            error_summary="prescription draft generation did not complete",
            attributes={
                "module": "prescription",
                "operation": "generate_draft",
                "success": False,
            },
        ),
        commit=False,
    )


async def _finish_prescription_cancellation_trace(
    *,
    traces: TraceService,
    tenant_id: str,
    trace_id: str | None,
    started_at: float | None,
) -> None:
    """Persist one PHI-free terminal cancellation and never create a draft."""

    if trace_id is None or started_at is None:
        return
    trace_suffix = trace_id.removeprefix("trace_")
    await traces.append_event(
        tenant_id,
        trace_id,
        TraceEventCreate(
            event_id=f"event_{trace_suffix}_generate_draft_cancelled",
            event_type=TraceEventType.CLINICAL_INTAKE,
            status=TraceEventStatus.CANCELLED,
            payload={
                "feature": "prescription",
                "operation": "generate_draft",
                "outcome": "cancelled",
                "success": False,
            },
            duration_ms=bounded_trace_duration_ms(monotonic() - started_at),
        ),
        commit=False,
    )
    await traces.finish_trace(
        tenant_id,
        trace_id,
        TraceFinishRequest(
            idempotency_key=f"finish_{trace_suffix}_cancelled",
            status=TraceStatus.CANCELLED,
            error_code="prescription_generation_cancelled",
            error_summary="prescription draft generation was cancelled",
            attributes={
                "module": "prescription",
                "operation": "generate_draft",
                "success": False,
            },
        ),
        commit=False,
    )


@router.post("", response_model=ClinicalIntakeRead, status_code=status.HTTP_201_CREATED)
async def start_intake(
    payload: ClinicalIntakeStartRequest,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    traces: TraceServiceDependency,
) -> ClinicalIntakeRead:
    """Create an encrypted collection record; it contains no clinical output."""

    await _enforce_rate_limit(request, identity)
    await _require_session(session, payload.session_id, identity)
    try:
        trace_id, started_at = await _start_write_trace(
            request=request,
            traces=traces,
            identity=identity,
            session_id=payload.session_id,
            kind=payload.kind,
            operation="start",
            payload=payload,
        )
    except TraceConflictError as error:
        raise HTTPException(
            status_code=409, detail={"code": "CLINICAL_INTAKE_TRACE_CONFLICT"}
        ) from error
    result = await _service(session, request).start(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        session_id=payload.session_id,
        kind=payload.kind,
    )
    await _finish_write_trace(
        traces=traces,
        tenant_id=identity.tenant_id,
        trace_id=trace_id,
        operation="start",
        elapsed_started_at=started_at,
        result=result,
    )
    await session.commit()
    return result


@router.post(
    "/{intake_id}/conversation-turn",
    response_model=PrescriptionConversationTurnRead,
)
async def process_prescription_conversation_turn(
    intake_id: uuid.UUID,
    payload: PrescriptionConversationTurnRequest,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    traces: TraceServiceDependency,
) -> PrescriptionConversationTurnRead:
    """Use the governed model to extract one normal chat turn into intake state."""

    await _enforce_rate_limit(request, identity)
    trace_id: str | None = None
    started_at: float | None = None
    attempts: list[ModelAttempt] = []
    try:
        service = _service(session, request)
        current = await service.get(
            intake_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
        if current.kind != "prescription":
            raise ClinicalIntakeConflictError("prescription conversation is unavailable")
        if current.conversation_turns >= 5:
            raise ClinicalIntakeConflictError("prescription clarification turn limit reached")
        trace_id, started_at = await _start_write_trace(
            request=request,
            traces=traces,
            identity=identity,
            session_id=current.session_id,
            kind="prescription",
            operation="conversation_turn",
            payload=payload,
        )
        if payload.images:
            await traces.record_private_input_artifacts(
                identity.tenant_id,
                trace_id,
                {"images": [image.trace_record() for image in payload.images]},
            )
        prepared, documents, stored_images = await service.prepare_prescription_conversation(
            intake_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            document_ids=payload.document_ids,
        )
        if prepared.revision != payload.expected_revision:
            raise ClinicalIntakeConflictError("intake has changed; refresh before updating")
        model = request.app.state.agent_model
        if model is None:
            raise PrescriptionIntakeExtractionError("prescription intake model is unavailable")
        with (
            bind_model_prompt_egress_audit(
                SqlAlchemyModelPromptEgressAudit(
                    request.app.state.database,
                    tenant_id=identity.tenant_id,
                    actor_id=identity.actor_id,
                )
            ),
            capture_model_attempts() as captured_attempts,
        ):
            try:
                extraction = await PrescriptionIntakeExtractor(
                    cast(StructuredIntakeModel, model)
                ).extract(
                    fields=intake_definition("prescription").fields,
                    existing_answers=prepared.answers,
                    documents=documents,
                    images=tuple([*stored_images, *payload.images]),
                    user_message=payload.message,
                )
            finally:
                attempts = list(captured_attempts)
        result = await service.update(
            intake_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            expected_revision=payload.expected_revision,
            answers=extraction.answer_updates,
            document_ids=payload.document_ids,
            images=payload.images,
            conversation_turn_increment=1,
        )
        await _append_model_attempt_events(
            traces=traces, tenant_id=identity.tenant_id, trace_id=trace_id, attempts=attempts
        )
        await _finish_write_trace(
            traces=traces,
            tenant_id=identity.tenant_id,
            trace_id=trace_id,
            operation="conversation_turn",
            elapsed_started_at=started_at,
            result=result,
        )
        await session.commit()
        if result.status == "information_complete_pending_governance":
            message = "资料已整理完成，正在生成五大处方草案。"  # noqa: RUF001
        else:
            message = extraction.follow_up_question or "请补充与本次目标最相关的情况。"
        return PrescriptionConversationTurnRead(
            intake=result,
            assistant_message=message,
            ready_to_generate=result.status == "information_complete_pending_governance",
        )
    except (
        ClinicalIntakeNotFoundError,
        ClinicalIntakeConflictError,
        PrescriptionIntakeExtractionError,
        TraceConflictError,
    ) as error:
        try:
            await _finish_conversation_failure_trace(
                traces=traces,
                tenant_id=identity.tenant_id,
                trace_id=trace_id,
                started_at=started_at,
                attempts=attempts,
            )
            await session.commit()
        except Exception:
            await session.rollback()
        error_code = (
            "PRESCRIPTION_INPUT_NOT_READY"
            if isinstance(error, (ClinicalIntakeNotFoundError, ClinicalIntakeConflictError))
            else "PRESCRIPTION_INTAKE_UNAVAILABLE"
        )
        status_code = 409 if error_code == "PRESCRIPTION_INPUT_NOT_READY" else 503
        raise HTTPException(status_code=status_code, detail={"code": error_code}) from error


@router.get(
    "/{intake_id}/medication-reconciliation",
    response_model=MedicationReconciliationRead,
)
async def get_medication_reconciliation(
    intake_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
) -> MedicationReconciliationRead:
    """Return a caller-owned list-quality preview, never a clinical review."""

    await _enforce_rate_limit(request, identity)
    try:
        intake = await _service(session, request).get(
            intake_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except ClinicalIntakeNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "CLINICAL_INTAKE_NOT_FOUND"}
        ) from error
    if intake.kind != "medication_review":
        raise HTTPException(
            status_code=409, detail={"code": "MEDICATION_RECONCILIATION_UNAVAILABLE"}
        )
    try:
        return reconcile_medication_list(
            intake_id=intake.intake_id,
            medication_list=intake.answers.get("medication_list", ""),
        )
    except MedicationReconciliationInputError as error:
        raise HTTPException(
            status_code=409, detail={"code": "MEDICATION_RECONCILIATION_INPUT_INVALID"}
        ) from error


@router.post(
    "/{intake_id}/medication-review-draft",
    response_model=MedicationReviewDraft,
)
async def generate_medication_review_draft(
    intake_id: uuid.UUID,
    payload: MedicationReviewRequest,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    traces: TraceServiceDependency,
) -> MedicationReviewDraft:
    """Evaluate the installed source-traceable medication rules for one owner."""

    await _enforce_rate_limit(request, identity)
    try:
        intake = await _service(session, request).get(
            intake_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except ClinicalIntakeNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "CLINICAL_INTAKE_NOT_FOUND"}
        ) from error
    if intake.kind != "medication_review":
        raise HTTPException(status_code=409, detail={"code": "MEDICATION_REVIEW_UNAVAILABLE"})
    try:
        result = review_medication_list(
            intake_id=intake.intake_id,
            medication_list=intake.answers.get("medication_list", ""),
            patient_age=payload.patient_age,
        )
    except MedicationRulesInputError as error:
        raise HTTPException(
            status_code=409, detail={"code": "MEDICATION_REVIEW_INPUT_INVALID"}
        ) from error

    trace_id = str(request.state.trace_id)
    set_active_trace(request.scope, trace_id)
    started_at = monotonic()
    trace_started = await traces.start_trace_with_status(
        TraceStartRequest(
            session_id=intake.session_id,
            execution_type="medication_review.generate",
            attributes={
                "feature": "medication_review",
                "module": "medication_review",
                "operation": "generate_draft",
                "version": result.ruleset_version,
                "request_fingerprint": audit_hmac_digest(
                    request.app.state.settings.auth_jwt_secret.get_secret_value().encode(),
                    f"{intake_id}:{payload.patient_age}".encode(),
                ),
            },
        ),
        str(request.state.request_id),
        trace_id=trace_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        commit=False,
    )
    if not trace_started.created:
        raise HTTPException(status_code=409, detail={"code": "MEDICATION_REVIEW_TRACE_CONFLICT"})
    await SqlAlchemyMedicationReviewDraftRepository(session).create(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        session_id=intake.session_id,
        clinical_intake_id=intake.intake_id,
        clinical_intake_revision=intake.revision,
        ruleset_version=result.ruleset_version,
        content=result.model_dump(mode="json"),
    )
    await RiskAlertService(SqlAlchemyRiskAlertRepository(session)).sync_medication_review(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        source_fingerprints=_medication_alert_fingerprints(
            request, intake_id=intake_id, result=result
        ),
        review=result,
    )
    trace_suffix = trace_id.removeprefix("trace_")
    await traces.append_event(
        identity.tenant_id,
        trace_id,
        TraceEventCreate(
            event_id=f"event_{trace_suffix}_generate_medication_review",
            event_type=TraceEventType.CLINICAL_INTAKE,
            status=TraceEventStatus.SUCCEEDED,
            payload={
                "feature": "medication_review",
                "operation": "generate_draft",
                "version": result.ruleset_version,
                "document_count": 0,
                "event_count": len(result.findings),
                "outcome": "needs_clinician_review",
                "success": True,
            },
            duration_ms=bounded_trace_duration_ms(monotonic() - started_at),
        ),
        commit=False,
    )
    await traces.finish_trace(
        identity.tenant_id,
        trace_id,
        TraceFinishRequest(
            idempotency_key=f"finish_{trace_suffix}",
            status=TraceStatus.COMPLETED,
            attributes={
                "module": "medication_review",
                "operation": "generate_draft",
                "version": result.ruleset_version,
                "success": True,
            },
        ),
        commit=False,
    )
    await session.commit()
    return result


@router.get(
    "/{intake_id}/medication-review-drafts",
    response_model=MedicationReviewDraftHistoryRead,
)
async def list_medication_review_drafts(
    intake_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
) -> MedicationReviewDraftHistoryRead:
    """Return bounded encrypted medication-review history for its owner only."""

    await _enforce_rate_limit(request, identity)
    try:
        intake = await SqlAlchemyClinicalIntakeRepository(session).get(
            intake_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except ClinicalIntakeNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "CLINICAL_INTAKE_NOT_FOUND"}
        ) from error
    if intake.kind != "medication_review":
        raise HTTPException(status_code=409, detail={"code": "MEDICATION_REVIEW_UNAVAILABLE"})

    records = await SqlAlchemyMedicationReviewDraftRepository(session).list_for_intake(
        intake_id=intake_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        limit=20,
    )
    return MedicationReviewDraftHistoryRead(
        items=tuple(
            MedicationReviewDraftRead(
                draft_id=record.id,
                intake_id=record.clinical_intake_id,
                intake_revision=record.clinical_intake_revision,
                created_at=record.created_at,
                draft=MedicationReviewDraft.model_validate(record.content),
            )
            for record in records
        )
    )


@router.get(
    "/{intake_id}/prescription-input",
    response_model=PrescriptionInputReadiness,
)
async def get_prescription_input_readiness(
    intake_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
) -> PrescriptionInputReadiness:
    """Validate complete private prescription inputs without returning their text.

    This is a material-readiness check, not report generation. It ensures that
    selected MinerU/local documents still belong to this caller and session and
    fit in the governed input budget before the reviewed-draft workflow uses
    them as uploaded input/provenance.
    """

    await _enforce_rate_limit(request, identity)
    try:
        return await _service(session, request).prescription_input_readiness(
            intake_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except ClinicalIntakeNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "CLINICAL_INTAKE_NOT_FOUND"}
        ) from error
    except ClinicalIntakeConflictError as error:
        raise HTTPException(
            status_code=409, detail={"code": "PRESCRIPTION_INPUT_NOT_READY"}
        ) from error


@router.post("/{intake_id}/prescription-draft", response_model=FivePrescriptionDraft)
async def generate_prescription_draft(
    intake_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    traces: TraceServiceDependency,
) -> FivePrescriptionDraft:
    """Generate one evidence-bound, clinician-review-only five-prescription draft."""

    await _enforce_rate_limit(request, identity)
    trace_id: str | None = None
    started_at: float | None = None
    attempts: list[ModelAttempt] = []
    registry: ChatCancellationRegistry = request.app.state.chat_cancellations
    registered_task: asyncio.Task[None] | None = None
    try:
        prepared = await _service(session, request).prepare_prescription_input(
            intake_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
        workflow = get_default_workflow_registry().validate_context(
            WorkflowId.PRESCRIPTION,
            loaded_skill_count=0,
            uploaded_file_count=len(prepared.uploaded_documents),
            uploaded_image_count=len(prepared.uploaded_images),
        )
        model = request.app.state.agent_model
        if model is None:
            raise PrescriptionGenerationError("prescription model is unavailable")
        trace_id = str(request.state.trace_id)
        set_active_trace(request.scope, trace_id)
        started_at = monotonic()
        trace_started = await traces.start_trace_with_status(
            TraceStartRequest(
                session_id=prepared.session_id,
                execution_type="prescription.generate",
                attributes={
                    "feature": "five_prescription",
                    "module": "prescription",
                    "operation": "generate_draft",
                    "workflow": workflow.workflow_id.value,
                    "workflow_version": workflow.version,
                    "version": prepared.input_template_version,
                    "request_fingerprint": audit_hmac_digest(
                        request.app.state.settings.auth_jwt_secret.get_secret_value().encode(),
                        str(intake_id).encode(),
                    ),
                },
            ),
            str(request.state.request_id),
            trace_id=trace_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            # The cancellation endpoint must be able to find this owner-bound
            # running trace before an expensive model request begins.
            commit=True,
        )
        if not trace_started.created:
            raise TraceConflictError("prescription generation trace is already in use")
        if prepared.uploaded_images:
            await traces.record_private_input_artifacts(
                identity.tenant_id,
                trace_id,
                {"images": [image.trace_record() for image in prepared.uploaded_images]},
            )
        current_task = asyncio.current_task()
        if current_task is None:  # pragma: no cover - FastAPI always supplies a task
            raise PrescriptionGenerationError("prescription cancellation task is unavailable")
        registered_task = current_task
        try:
            await registry.register(
                tenant_id=identity.tenant_id,
                actor_id=identity.actor_id,
                trace_id=trace_id,
                task=current_task,
            )
        except ChatCancellationUnavailable as error:
            raise PrescriptionGenerationError(
                "prescription cancellation coordination unavailable"
            ) from error
        with (
            bind_model_prompt_egress_audit(
                SqlAlchemyModelPromptEgressAudit(
                    request.app.state.database,
                    tenant_id=identity.tenant_id,
                    actor_id=identity.actor_id,
                )
            ),
            capture_model_attempts() as captured_attempts,
        ):
            try:
                async with asyncio.timeout(
                    request.app.state.settings.prescription_generation_timeout_seconds
                ):
                    draft = await EvidenceBoundPrescriptionGenerator(
                        model=cast(StructuredPrescriptionModel, model),
                        rag_module=request.app.state.rag_runtime.module,
                        online_search_module=request.app.state.search_runtime.module,
                    ).generate(prepared)
            except TimeoutError as error:
                raise PrescriptionGenerationError(
                    "prescription generation exceeded its Runtime budget"
                ) from error
            finally:
                attempts = list(captured_attempts)
        try:
            if await registry.is_cancel_requested(
                tenant_id=identity.tenant_id,
                actor_id=identity.actor_id,
                trace_id=trace_id,
            ):
                raise asyncio.CancelledError("explicit prescription cancellation requested")
        except ChatCancellationUnavailable as error:
            raise PrescriptionGenerationError(
                "prescription cancellation coordination unavailable"
            ) from error
        await SqlAlchemyPrescriptionDraftRepository(session).create(
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            session_id=prepared.session_id,
            clinical_intake_id=intake_id,
            template_version=draft.template_version,
            workflow_version=workflow.version,
            status=draft.status,
            content=draft.model_dump(mode="json"),
        )
        await traces.append_event(
            identity.tenant_id,
            trace_id,
            TraceEventCreate(
                event_id=f"event_{trace_id.removeprefix('trace_')}_generate_draft",
                event_type=TraceEventType.CLINICAL_INTAKE,
                status=TraceEventStatus.SUCCEEDED,
                payload={
                    "feature": "prescription",
                    "operation": "generate_draft",
                    "version": draft.template_version,
                    "document_count": len(prepared.uploaded_documents),
                    "event_count": len(draft.evidence_sources),
                    "outcome": draft.status,
                    "success": True,
                },
                duration_ms=bounded_trace_duration_ms(monotonic() - started_at),
            ),
            commit=False,
        )
        await traces.finish_trace(
            identity.tenant_id,
            trace_id,
            TraceFinishRequest(
                idempotency_key=f"finish_{trace_id.removeprefix('trace_')}",
                status=TraceStatus.COMPLETED,
                attributes={"module": "prescription", "operation": "generate_draft"},
            ),
        )
        await session.commit()
        return draft
    except asyncio.CancelledError:
        try:
            await _finish_prescription_cancellation_trace(
                traces=traces,
                tenant_id=identity.tenant_id,
                trace_id=trace_id,
                started_at=started_at,
            )
            await session.commit()
        except Exception:
            await session.rollback()
        raise
    except (
        PrescriptionRedFlagError,
        EvidenceUnavailableError,
        ClinicalIntakeNotFoundError,
        ClinicalIntakeConflictError,
        PrescriptionGenerationError,
        TraceConflictError,
        WorkflowContextError,
    ) as error:
        error_code = _prescription_error_code(error)
        try:
            await _finish_prescription_failure_trace(
                traces=traces,
                tenant_id=identity.tenant_id,
                trace_id=trace_id,
                started_at=started_at,
                attempts=attempts,
                error_code=error_code,
            )
            await session.commit()
        except Exception:
            await session.rollback()
        status_code = (
            409
            if error_code
            in {
                "PRESCRIPTION_EMERGENCY_BLOCKED",
                "PRESCRIPTION_INPUT_NOT_READY",
                "PRESCRIPTION_TRACE_CONFLICT",
            }
            else 503
        )
        raise HTTPException(status_code=status_code, detail={"code": error_code}) from error
    finally:
        if registered_task is not None and trace_id is not None:
            await registry.unregister(
                tenant_id=identity.tenant_id,
                actor_id=identity.actor_id,
                trace_id=trace_id,
                task=registered_task,
            )


@router.post(
    "/{intake_id}/prescription-draft/{trace_id}/cancel",
    response_model=PrescriptionGenerationCancelRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_prescription_generation(
    intake_id: uuid.UUID,
    trace_id: TraceIdPath,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
) -> PrescriptionGenerationCancelRead:
    """Request safe termination of the caller's own running prescription draft.

    The encrypted intake ownership check permits the startup race where the
    generator has not committed its Trace yet.  Once it has registered, the
    shared registry binds the cancellation to the same tenant/actor/Trace key;
    a different caller can never target this task.
    """

    await _enforce_rate_limit(request, identity)
    try:
        intake = await SqlAlchemyClinicalIntakeRepository(session).get(
            intake_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except ClinicalIntakeNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLINICAL_INTAKE_NOT_FOUND"},
        ) from error
    if intake.kind != "prescription":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "PRESCRIPTION_INTAKE_REQUIRED"},
        )
    registry: ChatCancellationRegistry = request.app.state.chat_cancellations
    try:
        await registry.request_cancel(
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            trace_id=trace_id,
        )
    except ChatCancellationUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "PRESCRIPTION_CANCELLATION_UNAVAILABLE",
                "message": "暂时无法安全停止, 请稍后重试。",
            },
        ) from error
    return PrescriptionGenerationCancelRead(trace_id=trace_id)


@router.get("/{intake_id}/prescription-drafts", response_model=PrescriptionDraftHistoryRead)
async def list_prescription_drafts(
    intake_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
) -> PrescriptionDraftHistoryRead:
    """Return at most twenty encrypted draft revisions owned by this caller."""

    await _enforce_rate_limit(request, identity)
    try:
        intake = await SqlAlchemyClinicalIntakeRepository(session).get(
            intake_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except ClinicalIntakeNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "CLINICAL_INTAKE_NOT_FOUND"}
        ) from error
    if intake.kind != "prescription":
        raise HTTPException(status_code=409, detail={"code": "PRESCRIPTION_INTAKE_REQUIRED"})

    records = await SqlAlchemyPrescriptionDraftRepository(session).list_for_intake(
        intake_id=intake_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        limit=20,
    )
    reviews = await SqlAlchemyPrescriptionDraftRepository(session).list_reviews_for_drafts(
        tenant_id=identity.tenant_id,
        draft_ids=tuple(record.id for record in records),
        doctor_actor_id=None,
    )
    reviews_by_draft: dict[uuid.UUID, list[PrescriptionDraftReviewRead]] = {}
    for review in reviews:
        reviews_by_draft.setdefault(review.prescription_draft_id, []).append(
            PrescriptionDraftReviewRead(
                review_id=review.id,
                draft_id=review.prescription_draft_id,
                doctor_actor_id=review.doctor_actor_id,
                decision=review.decision,
                review_note=review.review_note,
                revision=review.revision,
                reviewed_at=review.reviewed_at,
            )
        )
    return PrescriptionDraftHistoryRead(
        items=tuple(
            PrescriptionDraftRead(
                draft_id=record.id,
                intake_id=record.clinical_intake_id,
                created_at=record.created_at,
                draft=FivePrescriptionDraft.model_validate(record.content),
                reviews=tuple(reviews_by_draft.get(record.id, ())),
            )
            for record in records
        )
    )


@router.get("/{intake_id}", response_model=ClinicalIntakeRead)
async def get_intake(
    intake_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
) -> ClinicalIntakeRead:
    """Read only the authenticated caller's encrypted intake values."""

    await _enforce_rate_limit(request, identity)
    try:
        return await _service(session, request).get(
            intake_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
    except ClinicalIntakeNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "CLINICAL_INTAKE_NOT_FOUND"}
        ) from error


@router.patch("/{intake_id}", response_model=ClinicalIntakeRead)
async def update_intake(
    intake_id: uuid.UUID,
    payload: ClinicalIntakeUpdateRequest,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    traces: TraceServiceDependency,
) -> ClinicalIntakeRead:
    """Apply a fenced, server-validated answer update with no clinical interpretation."""

    await _enforce_rate_limit(request, identity)
    try:
        current = await _service(session, request).get(
            intake_id, tenant_id=identity.tenant_id, actor_id=identity.actor_id
        )
        trace_id, started_at = await _start_write_trace(
            request=request,
            traces=traces,
            identity=identity,
            session_id=current.session_id,
            kind=current.kind,
            operation="update",
            payload=payload,
        )
        result = await _service(session, request).update(
            intake_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            expected_revision=payload.expected_revision,
            answers=payload.answers,
            document_ids=payload.document_ids,
            conversation_turn_increment=payload.conversation_turn_increment,
        )
    except ClinicalIntakeNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "CLINICAL_INTAKE_NOT_FOUND"}
        ) from error
    except ClinicalIntakeConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "CLINICAL_INTAKE_CONFLICT"}) from error
    except TraceConflictError as error:
        raise HTTPException(
            status_code=409, detail={"code": "CLINICAL_INTAKE_TRACE_CONFLICT"}
        ) from error
    await _finish_write_trace(
        traces=traces,
        tenant_id=identity.tenant_id,
        trace_id=trace_id,
        operation="update",
        elapsed_started_at=started_at,
        result=result,
    )
    await session.commit()
    return result

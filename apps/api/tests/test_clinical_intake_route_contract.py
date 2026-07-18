"""Trace ownership and safe read-boundary contracts for intake routes."""

import asyncio
import uuid
from datetime import UTC, datetime
from time import monotonic
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from gerclaw_api.api.routes.clinical_intakes import (
    _finish_prescription_cancellation_trace,
    _finish_prescription_failure_trace,
    _medication_alert_fingerprints,
    _module_name,
    cancel_prescription_generation,
    generate_prescription_draft,
    get_medication_reconciliation,
    get_prescription_input_readiness,
    list_medication_review_drafts,
)
from gerclaw_api.domain.enums import TraceEventStatus, TraceEventType, TraceStatus
from gerclaw_api.domain.trace_schemas import (
    MAX_TRACE_EVENT_DURATION_MS,
    TraceEventCreate,
    TraceStartRequest,
)
from gerclaw_api.modules.medication_review.models import MedicationReviewDraftHistoryRead
from gerclaw_api.modules.medication_review.rules_engine import review_medication_list
from gerclaw_api.modules.prescription.models import (
    ClinicalIntakeFieldRead,
    ClinicalIntakeRead,
    PrescriptionDraftHistoryRead,
    PrescriptionInputReadiness,
)
from gerclaw_api.services.model_router import ModelAttempt


def test_clinical_intake_trace_uses_the_actual_domain_owner() -> None:
    assert _module_name("prescription") == "prescription"
    assert _module_name("medication_review") == "medication_review"


def test_medication_alert_fingerprints_do_not_retain_drug_text() -> None:
    intake_id = uuid.uuid4()
    review = review_medication_list(
        intake_id=intake_id,
        medication_list="瑞舒伐他汀 40mg 每日一次\n环孢素",
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(
                    auth_jwt_secret=SimpleNamespace(get_secret_value=lambda: "a" * 64)
                )
            )
        )
    )

    fingerprints = _medication_alert_fingerprints(request, intake_id=intake_id, result=review)  # type: ignore[arg-type]

    assert set(fingerprints) == {
        "ddi_rosuvastatin_cyclosporine",
        "dose_rosuvastatin_max_daily_20mg_1",
    }
    assert all(len(value) == 52 for value in fingerprints.values())
    assert "瑞舒伐他汀" not in str(fingerprints)
    assert "环孢素" not in str(fingerprints)


def test_prescription_draft_trace_metadata_obeys_the_audit_allowlist() -> None:
    """The live generation route must never turn a telemetry typo into HTTP 500."""

    start = TraceStartRequest(
        session_id=uuid.uuid4(),
        execution_type="prescription.generate",
        attributes={
            "feature": "five_prescription",
            "module": "prescription",
            "operation": "generate_draft",
            "workflow": "prescription",
            "workflow_version": "1.0.0",
            "version": "five-prescription-input-v1",
            "request_fingerprint": "a" * 52,
        },
    )
    event = TraceEventCreate(
        event_id="event_" + "a" * 32 + "_generate_draft",
        event_type=TraceEventType.CLINICAL_INTAKE,
        status=TraceEventStatus.SUCCEEDED,
        payload={
            "feature": "prescription",
            "operation": "generate_draft",
            "version": "five-prescription-report-v1",
            "document_count": 1,
            "event_count": 2,
            "outcome": "needs_clinician_review",
            "success": True,
        },
        duration_ms=1,
    )

    assert start.attributes["version"] == "five-prescription-input-v1"
    assert start.attributes["workflow"] == "prescription"
    assert event.payload["event_count"] == 2


def test_prescription_draft_history_is_bounded_and_strict() -> None:
    assert PrescriptionDraftHistoryRead.model_validate({}).items == ()
    with pytest.raises(ValueError):
        PrescriptionDraftHistoryRead.model_validate({"items": [], "extra": True})


def test_medication_review_draft_history_is_bounded_and_strict() -> None:
    assert MedicationReviewDraftHistoryRead.model_validate({}).items == ()
    with pytest.raises(ValueError):
        MedicationReviewDraftHistoryRead.model_validate({"items": [], "extra": True})


@pytest.mark.asyncio
async def test_medication_review_history_reads_only_the_owned_intake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    generated_at = datetime(2026, 7, 18, tzinfo=UTC)
    review = review_medication_list(
        intake_id=intake_id,
        medication_list="瑞舒伐他汀 40mg 每日一次\n环孢素",
    )

    class _Intakes:
        async def get(self, requested_id: uuid.UUID, **kwargs: object) -> object:
            assert requested_id == intake_id
            assert kwargs == {"tenant_id": "tenant", "actor_id": "actor"}
            return SimpleNamespace(kind="medication_review")

    class _Drafts:
        async def list_for_intake(self, **kwargs: object) -> list[object]:
            assert kwargs == {
                "intake_id": intake_id,
                "tenant_id": "tenant",
                "actor_id": "actor",
                "limit": 20,
            }
            return [
                SimpleNamespace(
                    id=draft_id,
                    clinical_intake_id=intake_id,
                    clinical_intake_revision=3,
                    created_at=generated_at,
                    content=review.model_dump(mode="json"),
                )
            ]

    async def _no_rate_limit(*_args: object, **_kwargs: object) -> None:
        return None

    from gerclaw_api.api.routes import clinical_intakes as intake_routes

    monkeypatch.setattr(
        intake_routes,
        "SqlAlchemyClinicalIntakeRepository",
        lambda _session: _Intakes(),
    )
    monkeypatch.setattr(
        intake_routes, "SqlAlchemyMedicationReviewDraftRepository", lambda _session: _Drafts()
    )
    monkeypatch.setattr(intake_routes, "_enforce_rate_limit", _no_rate_limit)

    result = await list_medication_review_drafts(
        intake_id,
        SimpleNamespace(),
        object(),
        SimpleNamespace(tenant_id="tenant", actor_id="actor"),
    )  # type: ignore[arg-type]

    assert result.items[0].draft_id == draft_id
    assert result.items[0].intake_revision == 3
    assert result.items[0].draft.findings[0].finding_id == "ddi_rosuvastatin_cyclosporine"


@pytest.mark.asyncio
async def test_prescription_failure_trace_keeps_slot_only_attempts() -> None:
    class _Traces:
        def __init__(self) -> None:
            self.events: list[TraceEventCreate] = []
            self.finish = None

        async def append_event(
            self, _tenant_id: str, _trace_id: str, event: TraceEventCreate, **_kwargs: object
        ) -> None:
            self.events.append(event)

        async def finish_trace(
            self, _tenant_id: str, _trace_id: str, payload: object, **_kwargs: object
        ) -> None:
            self.finish = payload

    traces = _Traces()
    await _finish_prescription_failure_trace(
        traces=traces,  # type: ignore[arg-type]
        tenant_id="tenant",
        trace_id="trace_" + "a" * 32,
        started_at=monotonic() - 90_000,
        attempts=[
            ModelAttempt(
                "primary",
                "failed",
                "MODEL_TIMEOUT",
                "model-capabilities-v1",
            ),
            ModelAttempt("backup1", "started"),
        ],
        error_code="PRESCRIPTION_DRAFT_UNAVAILABLE",
    )

    model_events = [
        event for event in traces.events if event.event_type is TraceEventType.MODEL_CALL
    ]
    assert [event.payload for event in model_events] == [
        {
            "model": "slot_primary",
            "capability_version": "model-capabilities-v1",
            "outcome": "failed",
            "success": False,
            "error_code": "model_timeout",
        },
        {"model": "slot_backup1", "outcome": "started", "success": False},
    ]
    assert traces.events[-1].event_type is TraceEventType.SYSTEM_ERROR
    assert traces.events[-1].payload["error_code"] == "prescription_draft_unavailable"
    assert traces.events[-1].duration_ms == MAX_TRACE_EVENT_DURATION_MS
    assert traces.finish is not None


@pytest.mark.asyncio
async def test_prescription_cancellation_finishes_without_private_input() -> None:
    class _Traces:
        def __init__(self) -> None:
            self.events: list[TraceEventCreate] = []
            self.finish = None

        async def append_event(
            self, _tenant_id: str, _trace_id: str, event: TraceEventCreate, **_kwargs: object
        ) -> None:
            self.events.append(event)

        async def finish_trace(
            self, _tenant_id: str, _trace_id: str, payload: object, **_kwargs: object
        ) -> None:
            self.finish = payload

    traces = _Traces()
    await _finish_prescription_cancellation_trace(
        traces=traces,  # type: ignore[arg-type]
        tenant_id="tenant",
        trace_id="trace_" + "a" * 32,
        started_at=monotonic() - 90_000,
    )

    assert len(traces.events) == 1
    event = traces.events[0]
    assert event.status is TraceEventStatus.CANCELLED
    assert event.payload == {
        "feature": "prescription",
        "operation": "generate_draft",
        "outcome": "cancelled",
        "success": False,
    }
    assert event.duration_ms == MAX_TRACE_EVENT_DURATION_MS
    assert traces.finish is not None
    assert traces.finish.status is TraceStatus.CANCELLED


@pytest.mark.asyncio
async def test_prescription_cancellation_is_scoped_to_the_owned_intake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_id = uuid.uuid4()
    trace_id = "trace_" + "a" * 32

    class _Repository:
        async def get(self, requested_id: uuid.UUID, **kwargs: object) -> object:
            assert requested_id == intake_id
            assert kwargs == {"tenant_id": "tenant", "actor_id": "actor"}
            return SimpleNamespace(kind="prescription")

    class _Registry:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        async def request_cancel(self, **kwargs: str) -> None:
            self.calls.append(kwargs)

    async def _no_rate_limit(*_args: object, **_kwargs: object) -> None:
        return None

    registry = _Registry()
    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes.SqlAlchemyClinicalIntakeRepository",
        lambda _session: _Repository(),
    )
    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes._enforce_rate_limit", _no_rate_limit
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(chat_cancellations=registry))
    )

    result = await cancel_prescription_generation(
        intake_id,
        trace_id,
        request,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        SimpleNamespace(tenant_id="tenant", actor_id="actor"),  # type: ignore[arg-type]
    )

    assert result.trace_id == trace_id
    assert result.status == "cancellation_requested"
    assert registry.calls == [{"tenant_id": "tenant", "actor_id": "actor", "trace_id": trace_id}]


@pytest.mark.asyncio
async def test_cancelled_prescription_generation_finishes_trace_without_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_id = uuid.uuid4()
    trace_id = "trace_" + "b" * 32
    session_id = uuid.uuid4()

    class _Service:
        async def prepare_prescription_input(
            self, requested_id: uuid.UUID, **kwargs: object
        ) -> object:
            assert requested_id == intake_id
            assert kwargs == {"tenant_id": "tenant", "actor_id": "actor"}
            return SimpleNamespace(
                uploaded_documents=(),
                uploaded_images=(),
                session_id=session_id,
                input_template_version="five-prescription-input-v1",
            )

    class _Traces:
        def __init__(self) -> None:
            self.start_commits: list[bool] = []
            self.events: list[TraceEventCreate] = []
            self.finished: list[object] = []

        async def start_trace_with_status(self, *_args: object, **kwargs: object) -> object:
            self.start_commits.append(kwargs["commit"])
            return SimpleNamespace(created=True)

        async def append_event(self, *_args: object, **kwargs: object) -> None:
            self.events.append(_args[2])

        async def finish_trace(self, *_args: object, **kwargs: object) -> None:
            self.finished.append(_args[2])

    class _Registry:
        def __init__(self) -> None:
            self.registered: list[dict[str, object]] = []
            self.unregistered: list[dict[str, object]] = []

        async def register(self, **kwargs: object) -> None:
            self.registered.append(kwargs)

        async def unregister(self, **kwargs: object) -> None:
            self.unregistered.append(kwargs)

        async def is_cancel_requested(self, **_kwargs: object) -> bool:
            return True

    class _Session:
        committed = 0
        rolled_back = 0

        async def commit(self) -> None:
            self.committed += 1

        async def rollback(self) -> None:
            self.rolled_back += 1

    async def _cancelled_generate(_prepared: object) -> object:
        raise asyncio.CancelledError("test cancellation")

    async def _no_rate_limit(*_args: object, **_kwargs: object) -> None:
        return None

    traces = _Traces()
    registry = _Registry()
    session = _Session()
    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes._service", lambda *_args: _Service()
    )
    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes._enforce_rate_limit",
        _no_rate_limit,
    )
    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes.get_default_workflow_registry",
        lambda: SimpleNamespace(
            validate_context=lambda *_args, **_kwargs: SimpleNamespace(
                workflow_id=SimpleNamespace(value="prescription"), version="1.0.0"
            )
        ),
    )
    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes.EvidenceBoundPrescriptionGenerator",
        lambda **_kwargs: SimpleNamespace(generate=_cancelled_generate),
    )
    request = SimpleNamespace(
        state=SimpleNamespace(
            trace_id=trace_id,
            request_id="req_" + "c" * 32,
            chat_cancellations=registry,
            settings=SimpleNamespace(
                prescription_generation_timeout_seconds=1,
                auth_jwt_secret=SimpleNamespace(get_secret_value=lambda: "a" * 64),
            ),
            agent_model=object(),
            rag_runtime=SimpleNamespace(module=object()),
            search_runtime=SimpleNamespace(module=object()),
            database=object(),
        ),
        app=SimpleNamespace(
            state=SimpleNamespace(
                chat_cancellations=registry,
                settings=SimpleNamespace(
                    prescription_generation_timeout_seconds=1,
                    auth_jwt_secret=SimpleNamespace(get_secret_value=lambda: "a" * 64),
                ),
                agent_model=object(),
                rag_runtime=SimpleNamespace(module=object()),
                search_runtime=SimpleNamespace(module=object()),
                database=object(),
            )
        ),
        scope={},
    )

    with pytest.raises(asyncio.CancelledError):
        await generate_prescription_draft(
            intake_id,
            request,  # type: ignore[arg-type]
            session,  # type: ignore[arg-type]
            SimpleNamespace(tenant_id="tenant", actor_id="actor"),  # type: ignore[arg-type]
            traces,  # type: ignore[arg-type]
        )

    assert traces.start_commits == [True]
    assert traces.events[-1].status is TraceEventStatus.CANCELLED
    assert traces.finished[-1].status is TraceStatus.CANCELLED
    assert registry.registered and registry.unregistered
    assert session.committed == 1


class _Request:
    app: object


@pytest.mark.asyncio
async def test_medication_reconciliation_is_unavailable_for_prescription_intake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Service:
        async def get(self, *_args: object, **_kwargs: object) -> ClinicalIntakeRead:
            return ClinicalIntakeRead(
                intake_id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                kind="prescription",
                definition_version="clinical-intake-v1",
                status="collecting",
                revision=1,
                conversation_turns=0,
                title="x",
                description="x",
                fields=[
                    ClinicalIntakeFieldRead(
                        id="health_goal", label="x", required=True, max_length=1, placeholder="x"
                    )
                ],
                answers={},
                document_ids=[],
                missing_required_fields=[],
                governance_notice="x",
                updated_at="2026-01-01T00:00:00Z",
            )

    async def _no_rate_limit(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes._service", lambda *_args: _Service()
    )
    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes._enforce_rate_limit", _no_rate_limit
    )
    with pytest.raises(HTTPException) as error:
        await get_medication_reconciliation(
            uuid.uuid4(),
            _Request(),
            object(),  # type: ignore[arg-type]
            SimpleNamespace(tenant_id="tenant", actor_id="actor"),  # type: ignore[arg-type]
        )
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_prescription_input_readiness_projects_counts_without_private_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_id = uuid.uuid4()

    class _Service:
        async def prescription_input_readiness(
            self, requested_id: uuid.UUID, **_kwargs: object
        ) -> PrescriptionInputReadiness:
            assert requested_id == intake_id
            return PrescriptionInputReadiness(
                intake_id=intake_id,
                definition_version="clinical-intake-v1",
                answer_field_count=2,
                uploaded_document_count=1,
                governance_notice="医生审核尚未启用。",
            )

    async def _no_rate_limit(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes._service", lambda *_args: _Service()
    )
    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes._enforce_rate_limit", _no_rate_limit
    )

    result = await get_prescription_input_readiness(
        intake_id,
        _Request(),
        object(),  # type: ignore[arg-type]
        SimpleNamespace(tenant_id="tenant", actor_id="actor"),  # type: ignore[arg-type]
    )

    payload = result.model_dump_json()
    assert result.uploaded_document_count == 1
    assert result.review_draft_enabled is True
    assert result.clinical_output_enabled is False
    assert "MinerU extracted report text" not in payload
    assert "health_goal" not in payload

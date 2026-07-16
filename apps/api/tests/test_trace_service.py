"""Unit tests for tenant isolation, idempotency, limits, and bad-case promotion."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.database.models import BadCase, ExecutionTrace, TraceEvent, UserFeedback
from gerclaw_api.domain.enums import FeedbackRating, TraceEventStatus, TraceEventType, TraceStatus
from gerclaw_api.domain.trace_schemas import (
    FeedbackCreate,
    TraceEventCreate,
    TraceFinishRequest,
    TraceStartRequest,
)
from gerclaw_api.services.trace_service import (
    TraceConflictError,
    TraceNotFoundError,
    TraceResourceLimitError,
    TraceService,
)

TENANT = "tenant_public0001"
ACTOR = "usr_patient_unit0001"
TRACE_ID = "trace_unit_0001"


class FakeTraceRepository:
    """In-memory repository preserving the production tenant-scoped contract."""

    def __init__(self) -> None:
        self.traces: dict[tuple[str, str], ExecutionTrace] = {}
        self.events: list[TraceEvent] = []
        self.feedback: dict[tuple[str, str], UserFeedback] = {}
        self.bad_cases: dict[tuple[str, str, str], BadCase] = {}
        self.commits = 0

    async def get_trace(
        self, tenant_id: str, trace_id: str, *, for_update: bool = False
    ) -> ExecutionTrace | None:
        del for_update
        return self.traces.get((tenant_id, trace_id))

    async def add_trace(self, trace: ExecutionTrace) -> None:
        self.traces[(trace.tenant_id, trace.trace_id)] = trace

    async def next_event_sequence(self, tenant_id: str, trace_id: str) -> int:
        return 1 + sum(
            event.tenant_id == tenant_id and event.trace_id == trace_id for event in self.events
        )

    async def add_event(self, event: TraceEvent) -> None:
        event.id = len(self.events) + 1
        event.created_at = datetime.now(UTC)
        self.events.append(event)

    async def get_event_by_id(
        self, tenant_id: str, trace_id: str, event_id: str
    ) -> TraceEvent | None:
        return next(
            (
                event
                for event in self.events
                if event.tenant_id == tenant_id
                and event.trace_id == trace_id
                and event.event_id == event_id
            ),
            None,
        )

    async def count_events(self, tenant_id: str, trace_id: str) -> int:
        return sum(
            event.tenant_id == tenant_id and event.trace_id == trace_id for event in self.events
        )

    async def list_events(
        self, tenant_id: str, trace_id: str, *, after_sequence: int, limit: int
    ) -> list[TraceEvent]:
        return [
            event
            for event in self.events
            if event.tenant_id == tenant_id
            and event.trace_id == trace_id
            and event.sequence > after_sequence
        ][:limit]

    async def get_feedback_by_key(
        self, tenant_id: str, idempotency_key: str
    ) -> UserFeedback | None:
        return self.feedback.get((tenant_id, idempotency_key))

    async def add_feedback(self, feedback: UserFeedback) -> None:
        feedback.id = uuid.uuid4()
        feedback.created_at = datetime.now(UTC)
        self.feedback[(feedback.tenant_id, feedback.idempotency_key)] = feedback

    async def get_bad_case(self, tenant_id: str, trace_id: str, source: str) -> BadCase | None:
        return self.bad_cases.get((tenant_id, trace_id, source))

    async def add_bad_case(self, bad_case: BadCase) -> None:
        self.bad_cases[(bad_case.tenant_id, bad_case.trace_id, bad_case.source)] = bad_case

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


def _start_request(**overrides: object) -> TraceStartRequest:
    values: dict[str, object] = {
        "execution_type": "agent.turn",
        "attributes": {"channel": "web"},
    }
    values.update(overrides)
    return TraceStartRequest.model_validate(values)


async def _start(service: TraceService, **overrides: object) -> ExecutionTrace:
    return await service.start_trace(
        _start_request(**overrides),
        "request_unit_001",
        trace_id=TRACE_ID,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )


@pytest.mark.asyncio
async def test_trace_lifecycle_is_idempotent_and_promotes_failure() -> None:
    repository = FakeTraceRepository()
    service = TraceService(repository)
    start_request = _start_request()
    trace = await _start(service)
    replay = await service.start_trace(
        start_request,
        "request_unit_002",
        trace_id=TRACE_ID,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    event_request = TraceEventCreate(
        event_id="event_unit_0001",
        event_type="tool.call",
        status="succeeded",
        payload={"tool_name": "medication.review", "success": True},
        duration_ms=17,
    )
    event = await service.append_event(TENANT, TRACE_ID, event_request)
    assert await service.append_event(TENANT, TRACE_ID, event_request) is event

    finish_request = TraceFinishRequest(
        idempotency_key="finish_unit_0001",
        status=TraceStatus.FAILED,
        error_code="tool_timeout",
        error_summary="联系 13900139000",
    )
    failed = await service.finish_trace(TENANT, TRACE_ID, finish_request)
    assert await service.finish_trace(TENANT, TRACE_ID, finish_request) is failed
    completed_replay = await service.start_trace(
        start_request,
        "request_unit_after_finish",
        trace_id=TRACE_ID,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert replay is trace
    assert completed_replay is trace
    assert trace.start_fingerprint is not None
    assert trace.attributes == {"channel": "web"}
    assert event.sequence == 1
    assert failed.error_summary == "联系 [PHONE]"
    assert (TENANT, TRACE_ID, "execution_failure") in repository.bad_cases

    changed_finish = finish_request.model_copy(update={"error_code": "another_error"})
    with pytest.raises(TraceConflictError):
        await service.finish_trace(TENANT, TRACE_ID, changed_finish)
    with pytest.raises(TraceConflictError):
        await service.append_event(
            TENANT,
            TRACE_ID,
            event_request.model_copy(update={"event_id": "event_unit_0002"}),
        )


@pytest.mark.asyncio
async def test_clinical_intake_trace_event_is_count_only_and_phi_free() -> None:
    repository = FakeTraceRepository()
    service = TraceService(repository)
    await _start(service)

    event = await service.append_event(
        TENANT,
        TRACE_ID,
        TraceEventCreate(
            event_id="event_intake_0001",
            event_type=TraceEventType.CLINICAL_INTAKE,
            status=TraceEventStatus.SUCCEEDED,
            payload={
                "feature": "prescription",
                "operation": "update",
                "version": "clinical-intake-v1",
                "event_count": 2,
                "document_count": 1,
                "outcome": "information_complete_pending_governance",
                "success": True,
            },
        ),
    )

    assert event.payload == {
        "feature": "prescription",
        "operation": "update",
        "version": "clinical-intake-v1",
        "event_count": 2,
        "document_count": 1,
        "outcome": "information_complete_pending_governance",
        "success": True,
    }


@pytest.mark.asyncio
async def test_cga_assessment_trace_event_is_count_only_and_phi_free() -> None:
    repository = FakeTraceRepository()
    service = TraceService(repository)
    await _start(service)

    event = await service.append_event(
        TENANT,
        TRACE_ID,
        TraceEventCreate(
            event_id="event_cga_0001",
            event_type=TraceEventType.CGA_ASSESSMENT,
            status=TraceEventStatus.SUCCEEDED,
            payload={
                "feature": "cga",
                "operation": "answer",
                "scale": "phq9",
                "version": "phq9-v1",
                "answered_count": 1,
                "outcome": "active",
                "success": True,
            },
        ),
    )

    assert event.payload == {
        "feature": "cga",
        "operation": "answer",
        "scale": "phq9",
        "version": "phq9-v1",
        "answered_count": 1,
        "outcome": "active",
        "success": True,
    }


@pytest.mark.asyncio
async def test_trace_start_status_distinguishes_creator_from_replay() -> None:
    repository = FakeTraceRepository()
    service = TraceService(repository)
    created = await service.start_trace_with_status(
        _start_request(),
        "request_unit_creator",
        trace_id=TRACE_ID,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )
    replayed = await service.start_trace_with_status(
        _start_request(),
        "request_unit_replay",
        trace_id=TRACE_ID,
        tenant_id=TENANT,
        actor_id=ACTOR,
    )

    assert created.created is True
    assert replayed.created is False
    assert replayed.trace is created.trace


@pytest.mark.asyncio
async def test_feedback_identity_and_tenant_are_derived_and_isolated() -> None:
    repository = FakeTraceRepository()
    service = TraceService(repository)
    trace = await _start(service)

    with pytest.raises(TraceConflictError):
        await service.start_trace(
            _start_request(),
            "request_unit_002",
            trace_id=TRACE_ID,
            tenant_id=TENANT,
            actor_id="usr_patient_different0001",
        )

    request = FeedbackCreate(
        idempotency_key="idem_unit_0001",
        trace_id=trace.trace_id,
        rating=FeedbackRating.NEGATIVE,
        categories=["unsafe_answer", "unsafe_answer"],
        comment="电话 13800138000",
        metadata={"channel": "web"},
    )
    feedback = await service.submit_feedback(request, tenant_id=TENANT, actor_id=ACTOR)
    replay = await service.submit_feedback(request, tenant_id=TENANT, actor_id=ACTOR)

    assert replay is feedback
    assert feedback.categories == ["unsafe_answer"]
    assert feedback.comment == "电话 [PHONE]"
    assert (TENANT, TRACE_ID, "negative_feedback") in repository.bad_cases
    with pytest.raises(TraceNotFoundError):
        await service.submit_feedback(
            request,
            tenant_id="tenant_another0001",
            actor_id=ACTOR,
        )


@pytest.mark.asyncio
async def test_missing_invalid_and_resource_limited_transitions_fail() -> None:
    repository = FakeTraceRepository()
    service = TraceService(repository, max_events_per_trace=1)

    with pytest.raises(TraceNotFoundError):
        await service.get_trace(TENANT, "trace_missing_0001")
    trace = await _start(service)
    event = TraceEventCreate(
        event_id="event_limit_0001",
        event_type="safety.check",
        status="succeeded",
        payload={"success": True},
    )
    await service.append_event(TENANT, trace.trace_id, event)
    with pytest.raises(TraceResourceLimitError):
        await service.append_event(
            TENANT,
            trace.trace_id,
            event.model_copy(update={"event_id": "event_limit_0002"}),
        )

    invalid_finish = TraceFinishRequest(
        idempotency_key="finish_unit_0002",
        status=TraceStatus.RUNNING,
    )
    with pytest.raises(TraceConflictError):
        await service.finish_trace(TENANT, trace.trace_id, invalid_finish)

    page, cursor = await service.list_events(TENANT, trace.trace_id, after_sequence=0, limit=1)
    assert len(page) == 1
    assert cursor is None


@pytest.mark.asyncio
async def test_success_events_can_be_flushed_as_one_uncommitted_unit() -> None:
    repository = FakeTraceRepository()
    service = TraceService(repository)
    await _start(service)
    commits_after_start = repository.commits
    await service.append_event(
        TENANT,
        TRACE_ID,
        TraceEventCreate(
            event_id="event_atomic_0001",
            event_type="agent.finish",
            status="succeeded",
            payload={"success": True},
        ),
        commit=False,
    )
    await service.finish_trace(
        TENANT,
        TRACE_ID,
        TraceFinishRequest(
            idempotency_key="finish_atomic_0001",
            status=TraceStatus.COMPLETED,
        ),
        commit=False,
    )
    assert repository.commits == commits_after_start
    assert repository.traces[(TENANT, TRACE_ID)].status == TraceStatus.COMPLETED.value

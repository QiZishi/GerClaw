"""Tenant-scoped transactional trace, feedback, and bad-case workflows."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from gerclaw_api.database.models import BadCase, ExecutionTrace, TraceEvent, UserFeedback
from gerclaw_api.domain.enums import BadCaseSource, FeedbackRating, TraceStatus
from gerclaw_api.domain.trace_schemas import (
    FeedbackCreate,
    TraceEventCreate,
    TraceFinishRequest,
    TraceStartRequest,
)
from gerclaw_api.repositories.trace import DuplicateKeyError, TraceRepository
from gerclaw_api.security import sanitize_payload


class TraceNotFoundError(LookupError):
    """Raised when a referenced execution trace is absent from the caller tenant."""


class TraceConflictError(RuntimeError):
    """Raised when an idempotent request conflicts with durable state."""


class TraceResourceLimitError(RuntimeError):
    """Raised when one Trace reaches its configured event ceiling."""


def _sanitized_dict(value: dict[str, Any]) -> dict[str, Any]:
    sanitized = sanitize_payload(value)
    if not isinstance(sanitized, dict):  # pragma: no cover - defensive invariant
        raise TypeError("sanitized dictionary changed type")
    return sanitized


def _finish_fingerprint(request: TraceFinishRequest) -> str:
    canonical = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class TraceService:
    """Maintain isolation, idempotency, and bounded-resource invariants."""

    def __init__(self, repository: TraceRepository, *, max_events_per_trace: int = 10_000) -> None:
        self._repository = repository
        self._max_events_per_trace = max_events_per_trace

    async def start_trace(
        self,
        request: TraceStartRequest,
        request_id: str,
        *,
        trace_id: str,
        tenant_id: str,
        actor_id: str,
    ) -> ExecutionTrace:
        existing = await self._repository.get_trace(tenant_id, trace_id)
        if existing is not None:
            self._validate_replayed_start(existing, request, actor_id)
            return existing

        trace = ExecutionTrace(
            trace_id=trace_id,
            request_id=request_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            session_id=request.session_id,
            execution_type=request.execution_type,
            status=TraceStatus.RUNNING.value,
            attributes=_sanitized_dict(request.attributes),
            started_at=datetime.now(UTC),
        )
        await self._repository.add_trace(trace)
        try:
            await self._repository.commit()
        except DuplicateKeyError:
            existing = await self._repository.get_trace(tenant_id, trace_id)
            if existing is None:  # pragma: no cover - database invariant
                raise
            self._validate_replayed_start(existing, request, actor_id)
            return existing
        return trace

    async def get_trace(self, tenant_id: str, trace_id: str) -> ExecutionTrace:
        trace = await self._repository.get_trace(tenant_id, trace_id)
        if trace is None:
            raise TraceNotFoundError(trace_id)
        return trace

    async def append_event(
        self, tenant_id: str, trace_id: str, request: TraceEventCreate
    ) -> TraceEvent:
        existing_event = await self._repository.get_event_by_id(
            tenant_id, trace_id, request.event_id
        )
        if existing_event is not None:
            self._validate_replayed_event(existing_event, request)
            return existing_event

        trace = await self._repository.get_trace(tenant_id, trace_id, for_update=True)
        if trace is None:
            raise TraceNotFoundError(trace_id)
        if trace.status != TraceStatus.RUNNING.value:
            raise TraceConflictError(f"trace {trace_id} is already {trace.status}")
        if await self._repository.count_events(tenant_id, trace_id) >= self._max_events_per_trace:
            raise TraceResourceLimitError(f"trace {trace_id} reached its event limit")

        event = TraceEvent(
            tenant_id=tenant_id,
            trace_id=trace_id,
            event_id=request.event_id,
            sequence=await self._repository.next_event_sequence(tenant_id, trace_id),
            event_type=request.event_type.value,
            status=request.status.value,
            payload=_sanitized_dict(request.payload),
            duration_ms=request.duration_ms,
        )
        await self._repository.add_event(event)
        try:
            await self._repository.commit()
        except DuplicateKeyError:
            existing_event = await self._repository.get_event_by_id(
                tenant_id, trace_id, request.event_id
            )
            if existing_event is None:  # pragma: no cover - database invariant
                raise
            self._validate_replayed_event(existing_event, request)
            return existing_event
        return event

    async def finish_trace(
        self, tenant_id: str, trace_id: str, request: TraceFinishRequest
    ) -> ExecutionTrace:
        if request.status is TraceStatus.RUNNING:
            raise TraceConflictError("a trace cannot be finished with running status")

        fingerprint = _finish_fingerprint(request)
        trace = await self._repository.get_trace(tenant_id, trace_id, for_update=True)
        if trace is None:
            raise TraceNotFoundError(trace_id)
        if trace.status != TraceStatus.RUNNING.value:
            if (
                trace.finish_idempotency_key == request.idempotency_key
                and trace.finish_fingerprint == fingerprint
            ):
                return trace
            raise TraceConflictError(f"trace {trace_id} was already finished with another payload")

        completed_at = datetime.now(UTC)
        trace.status = request.status.value
        trace.completed_at = completed_at
        trace.duration_ms = max(0, int((completed_at - trace.started_at).total_seconds() * 1_000))
        trace.error_code = request.error_code
        sanitized_summary = sanitize_payload(request.error_summary)
        trace.error_summary = sanitized_summary if isinstance(sanitized_summary, str) else None
        trace.attributes = {**trace.attributes, **_sanitized_dict(request.attributes)}
        trace.finish_idempotency_key = request.idempotency_key
        trace.finish_fingerprint = fingerprint

        if request.status is TraceStatus.FAILED:
            await self._add_bad_case_if_missing(
                trace=trace,
                source=BadCaseSource.EXECUTION_FAILURE,
                feedback=None,
                reason_codes=[request.error_code or "execution_failed"],
                severity="high",
            )
        await self._repository.commit()
        return trace

    async def list_events(
        self,
        tenant_id: str,
        trace_id: str,
        *,
        after_sequence: int,
        limit: int,
    ) -> tuple[list[TraceEvent], int | None]:
        await self.get_trace(tenant_id, trace_id)
        events = await self._repository.list_events(
            tenant_id, trace_id, after_sequence=after_sequence, limit=limit + 1
        )
        if len(events) <= limit:
            return events, None
        page = events[:limit]
        return page, page[-1].sequence

    async def submit_feedback(
        self, request: FeedbackCreate, *, tenant_id: str, actor_id: str
    ) -> UserFeedback:
        existing = await self._repository.get_feedback_by_key(tenant_id, request.idempotency_key)
        if existing is not None:
            self._validate_replayed_feedback(existing, request, actor_id)
            return existing

        trace = await self._repository.get_trace(tenant_id, request.trace_id, for_update=True)
        if trace is None or trace.actor_id != actor_id:
            raise TraceNotFoundError(request.trace_id)
        existing = await self._repository.get_feedback_by_key(tenant_id, request.idempotency_key)
        if existing is not None:
            self._validate_replayed_feedback(existing, request, actor_id)
            return existing

        sanitized_comment = sanitize_payload(request.comment)
        feedback = UserFeedback(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            idempotency_key=request.idempotency_key,
            trace_id=request.trace_id,
            actor_id=actor_id,
            rating=request.rating.value,
            categories=list(dict.fromkeys(request.categories)),
            comment=sanitized_comment if isinstance(sanitized_comment, str) else None,
            feedback_metadata=_sanitized_dict(request.metadata),
        )
        await self._repository.add_feedback(feedback)
        try:
            await self._repository.flush()
        except DuplicateKeyError:
            existing = await self._repository.get_feedback_by_key(
                tenant_id, request.idempotency_key
            )
            if existing is None:  # pragma: no cover - database invariant
                raise
            self._validate_replayed_feedback(existing, request, actor_id)
            return existing

        if request.rating is FeedbackRating.NEGATIVE:
            await self._add_bad_case_if_missing(
                trace=trace,
                source=BadCaseSource.NEGATIVE_FEEDBACK,
                feedback=feedback,
                reason_codes=feedback.categories or ["negative_feedback"],
                severity="medium",
            )
        try:
            await self._repository.commit()
        except DuplicateKeyError:
            existing = await self._repository.get_feedback_by_key(
                tenant_id, request.idempotency_key
            )
            if existing is None:  # pragma: no cover - database invariant
                raise
            self._validate_replayed_feedback(existing, request, actor_id)
            return existing
        return feedback

    async def _add_bad_case_if_missing(
        self,
        *,
        trace: ExecutionTrace,
        source: BadCaseSource,
        feedback: UserFeedback | None,
        reason_codes: list[str],
        severity: str,
    ) -> None:
        existing = await self._repository.get_bad_case(
            trace.tenant_id, trace.trace_id, source.value
        )
        if existing is not None:
            return
        snapshot: dict[str, Any] = {
            "execution_type": trace.execution_type,
            "trace_status": trace.status,
            "error_code": trace.error_code,
            "error_summary": trace.error_summary,
            "trace_attributes": trace.attributes,
        }
        if feedback is not None:
            snapshot["feedback"] = {
                "rating": feedback.rating,
                "categories": feedback.categories,
                "comment": feedback.comment,
                "metadata": feedback.feedback_metadata,
            }
        bad_case = BadCase(
            tenant_id=trace.tenant_id,
            trace_id=trace.trace_id,
            feedback_id=feedback.id if feedback is not None else None,
            source=source.value,
            reason_codes=reason_codes,
            severity=severity,
            status="open",
            snapshot=_sanitized_dict(snapshot),
        )
        await self._repository.add_bad_case(bad_case)

    @staticmethod
    def _validate_replayed_start(
        existing: ExecutionTrace, request: TraceStartRequest, actor_id: str
    ) -> None:
        identity = (
            existing.actor_id,
            existing.session_id,
            existing.execution_type,
            existing.attributes,
        )
        replay = (
            actor_id,
            request.session_id,
            request.execution_type,
            _sanitized_dict(request.attributes),
        )
        if identity != replay:
            raise TraceConflictError("trace ID was already used with different execution fields")

    @staticmethod
    def _validate_replayed_event(existing: TraceEvent, request: TraceEventCreate) -> None:
        if (
            existing.event_type != request.event_type.value
            or existing.status != request.status.value
            or existing.payload != _sanitized_dict(request.payload)
            or existing.duration_ms != request.duration_ms
        ):
            raise TraceConflictError("event ID was already used with a different payload")

    @staticmethod
    def _validate_replayed_feedback(
        existing: UserFeedback, request: FeedbackCreate, actor_id: str
    ) -> None:
        sanitized_comment = sanitize_payload(request.comment)
        if (
            existing.trace_id != request.trace_id
            or existing.actor_id != actor_id
            or existing.rating != request.rating.value
            or existing.categories != list(dict.fromkeys(request.categories))
            or existing.comment != sanitized_comment
            or existing.feedback_metadata != _sanitized_dict(request.metadata)
        ):
            raise TraceConflictError("idempotency key was already used for different feedback")

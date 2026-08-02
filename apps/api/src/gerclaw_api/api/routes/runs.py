"""Owner-scoped Agent Run, replay, answer, artifact, and feedback APIs."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.api.sse import encode_sse
from gerclaw_api.auth import (
    AuthContext,
    require_chat_read,
    require_chat_write,
    require_feedback_write,
)
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.domain.chat_error_codes import public_chat_fallback
from gerclaw_api.domain.chat_schemas import ChatCancelledData, ChatErrorData
from gerclaw_api.domain.run_schemas import (
    RUN_EVENT_CLOSED_STATUSES,
    AgentRunRead,
    AnswerVersionListRead,
    AnswerVersionRead,
    AnswerVersionSelect,
    ArtifactDeleted,
    ArtifactListRead,
    ArtifactRead,
    ArtifactWrite,
    FeedbackReconcileRequest,
    FeedbackStateRead,
    RecoverableRunRead,
    RunDirectiveListRead,
    RunDirectivePublicRead,
    RunEventPage,
    RunEventRead,
    RunQueuedDirectiveCreate,
)
from gerclaw_api.domain.trace_schemas import TRACE_ID_PATTERN
from gerclaw_api.repositories.agent_run import SqlAlchemyAgentRunRepository
from gerclaw_api.repositories.answer_version import SqlAlchemyAnswerVersionRepository
from gerclaw_api.repositories.run_artifact import SqlAlchemyRunArtifactRepository
from gerclaw_api.repositories.run_directive import SqlAlchemyRunDirectiveRepository
from gerclaw_api.repositories.run_feedback import SqlAlchemyRunFeedbackRepository
from gerclaw_api.repositories.run_resume import SqlAlchemyRunResumeRepository
from gerclaw_api.services.agent_run_service import AgentRunService
from gerclaw_api.services.answer_version_service import AnswerVersionService
from gerclaw_api.services.chat_cancellation import (
    ChatCancellationRegistry,
    ChatCancellationUnavailable,
)
from gerclaw_api.services.rate_limit import RateLimiter
from gerclaw_api.services.run_artifact_service import RunArtifactService
from gerclaw_api.services.run_directive_service import RunDirectiveService
from gerclaw_api.services.run_feedback_service import RunFeedbackService
from gerclaw_api.services.run_resume_service import RunResumeService

router = APIRouter(tags=["agent-runs"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
ReadIdentity = Annotated[AuthContext, Depends(require_chat_read)]
WriteIdentity = Annotated[AuthContext, Depends(require_chat_write)]
FeedbackIdentity = Annotated[AuthContext, Depends(require_feedback_write)]
TraceIdPath = Annotated[str, Path(pattern=TRACE_ID_PATTERN)]


async def _enforce_rate_limit(request: Request, identity: AuthContext) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)


def _run_service(session: AsyncSession) -> AgentRunService:
    return AgentRunService(SqlAlchemyAgentRunRepository(session))


def _answer_service(session: AsyncSession) -> AnswerVersionService:
    return AnswerVersionService(SqlAlchemyAnswerVersionRepository(session))


def _artifact_service(session: AsyncSession) -> RunArtifactService:
    return RunArtifactService(SqlAlchemyRunArtifactRepository(session))


def _feedback_service(session: AsyncSession) -> RunFeedbackService:
    return RunFeedbackService(SqlAlchemyRunFeedbackRepository(session))


def _directive_service(session: AsyncSession) -> RunDirectiveService:
    return RunDirectiveService(SqlAlchemyRunDirectiveRepository(session))


def _resume_service(session: AsyncSession) -> RunResumeService:
    return RunResumeService(SqlAlchemyRunResumeRepository(session))


@router.get("/runs/{run_id}", response_model=AgentRunRead)
async def get_run(
    run_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
) -> AgentRunRead:
    """Return the caller-owned durable Run state."""

    await _enforce_rate_limit(request, identity)
    return await _run_service(session).get_run(
        run_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )


@router.get(
    "/conversations/{conversation_id}/recoverable-run",
    response_model=RecoverableRunRead,
)
async def get_recoverable_run(
    conversation_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
) -> RecoverableRunRead:
    """Return the newest interrupted Run that this conversation may explicitly resume."""

    await _enforce_rate_limit(request, identity)
    run = await _resume_service(session).latest_recoverable(
        conversation_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )
    return RecoverableRunRead(conversation_id=conversation_id, run=run)


@router.get("/runs/{run_id}/events", response_model=RunEventPage)
async def replay_run_events(
    run_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> RunEventPage:
    """Replay a bounded sequence page after the caller's last durable event."""

    await _enforce_rate_limit(request, identity)
    events = await _run_service(session).list_events(
        run_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    return RunEventPage(
        run_id=run_id,
        events=tuple(events),
        next_after_sequence=events[-1].sequence if events else after_sequence,
    )


@router.get("/runs/{run_id}/stream")
async def stream_run_events(
    run_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    """Replay and follow one owner-scoped Run from the last durable sequence."""

    await _enforce_rate_limit(request, identity)
    run = await _run_service(session).get_run(
        run_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )
    await session.rollback()
    database = request.app.state.database
    poll_interval = request.app.state.settings.agent_run_stream_poll_interval_seconds
    heartbeat_interval = request.app.state.settings.agent_run_stream_heartbeat_seconds

    async def event_stream() -> AsyncIterator[str]:
        cursor = after_sequence
        last_heartbeat = time.monotonic()
        while True:
            async with database.session() as poll_session:
                service = _run_service(poll_session)
                current = await service.get_run(
                    run_id,
                    tenant_id=identity.tenant_id,
                    actor_id=identity.actor_id,
                )
                events = await service.list_events(
                    run_id,
                    tenant_id=identity.tenant_id,
                    actor_id=identity.actor_id,
                    after_sequence=cursor,
                    limit=500,
                )
            for event in events:
                cursor = event.sequence
                yield _encode_run_event(event, trace_id=current.trace_id)
                last_heartbeat = time.monotonic()
            if current.status in RUN_EVENT_CLOSED_STATUSES and cursor >= current.last_sequence:
                return
            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_interval:
                yield ": heartbeat\n\n"
                last_heartbeat = now
            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Trace-ID": run.trace_id,
            "X-Run-ID": str(run.id),
        },
    )


def _encode_run_event(event: RunEventRead, *, trace_id: str) -> str:
    """Project a validated durable event back to the public chat protocol."""

    timestamp = event.created_at.timestamp()
    if event.event_type == "run.status":
        if event.status == "cancelled":
            cancelled = ChatCancelledData(trace_id=trace_id).model_dump(mode="json")
            cancelled.update(
                {
                    "run_id": str(event.run_id),
                    "sequence": event.sequence,
                    "timestamp": timestamp,
                }
            )
            return encode_sse("cancelled", cancelled, sequence=event.sequence)
        code = "CHAT_RUN_INTERRUPTED" if event.status == "interrupted" else "CHAT_EXECUTION_FAILED"
        message, _retriable = public_chat_fallback(code)
        failed = ChatErrorData(
            code=code,
            message=message,
            trace_id=trace_id,
            retriable=True,
        ).model_dump(mode="json")
        failed.update(
            {
                "run_id": str(event.run_id),
                "sequence": event.sequence,
                "timestamp": timestamp,
            }
        )
        return encode_sse("error", failed, sequence=event.sequence)

    payload = dict(event.payload)
    payload.update(
        {
            "run_id": str(event.run_id),
            "sequence": event.sequence,
            "timestamp": timestamp,
        }
    )
    event_name = event.event_type
    if event.event_type in {"reasoning_summary", "run.resumed"}:
        event_name = "thinking"
        if event.event_type == "run.resumed":
            payload = {
                "content": event.public_summary or "已恢复执行",
                "status": "running",
                "run_id": str(event.run_id),
                "sequence": event.sequence,
                "timestamp": timestamp,
            }
    return encode_sse(event_name, payload, sequence=event.sequence)


@router.post("/runs/{run_id}/cancel", response_model=AgentRunRead)
async def cancel_run(
    run_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
) -> AgentRunRead:
    """Persist owner cancellation, then fan it out to an active worker."""

    await _enforce_rate_limit(request, identity)
    run = await _run_service(session).cancel_owned(
        run_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )
    request.app.state.evolution_signal_collector.schedule(run_id)
    registry: ChatCancellationRegistry = request.app.state.chat_cancellations
    try:
        await registry.request_cancel(
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            trace_id=run.trace_id,
        )
    except ChatCancellationUnavailable as error:
        # Durable cancellation already fences terminal writes. A 503 truthfully
        # reports that immediate worker fan-out could not be confirmed.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "RUN_CANCELLATION_FANOUT_UNAVAILABLE",
                "message": "取消已保存, 但暂时无法确认执行节点已收到通知。",
            },
        ) from error
    return run


@router.post(
    "/chat/{trace_id}/directives/queue",
    response_model=RunDirectivePublicRead,
    status_code=status.HTTP_201_CREATED,
)
async def queue_run_directive(
    trace_id: TraceIdPath,
    payload: RunQueuedDirectiveCreate,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
) -> RunDirectivePublicRead:
    """Persist a requirement for the next fenced model/tool boundary."""

    await _enforce_rate_limit(request, identity)
    directive = await _directive_service(session).queue_for_trace(
        trace_id,
        payload,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        wait_seconds=request.app.state.settings.agent_directive_trace_wait_seconds,
        poll_interval_seconds=(request.app.state.settings.agent_run_stream_poll_interval_seconds),
    )
    return RunDirectivePublicRead.from_internal(directive)


@router.get(
    "/runs/{run_id}/directives",
    response_model=RunDirectiveListRead,
)
async def list_run_directives(
    run_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> RunDirectiveListRead:
    """Return ordered owner-visible steer/queue status for one Run."""

    await _enforce_rate_limit(request, identity)
    directives = await _directive_service(session).list_for_run(
        run_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        limit=limit,
    )
    return RunDirectiveListRead(
        run_id=run_id,
        directives=tuple(RunDirectivePublicRead.from_internal(item) for item in directives),
    )


@router.delete(
    "/run-directives/{directive_id}",
    response_model=RunDirectivePublicRead,
)
async def cancel_unclaimed_run_directive(
    directive_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
) -> RunDirectivePublicRead:
    """Withdraw an instruction only while no worker boundary owns it."""

    await _enforce_rate_limit(request, identity)
    directive = await _directive_service(session).cancel_unclaimed(
        directive_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )
    return RunDirectivePublicRead.from_internal(directive)


@router.get(
    "/runs/{run_id}/answer-versions",
    response_model=AnswerVersionListRead,
)
async def list_answer_versions(
    run_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AnswerVersionListRead:
    """Return immutable answer history and its current marker."""

    await _enforce_rate_limit(request, identity)
    versions = await _answer_service(session).list_versions(
        run_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        limit=limit,
    )
    return AnswerVersionListRead(run_id=run_id, versions=tuple(versions))


@router.put(
    "/runs/{run_id}/answer-versions/{version_id}/current",
    response_model=AnswerVersionRead,
)
async def select_answer_version(
    run_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: AnswerVersionSelect,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
) -> AnswerVersionRead:
    """Select a prior answer without deleting or rewriting later versions."""

    await _enforce_rate_limit(request, identity)
    return await _answer_service(session).select(
        run_id,
        version_id,
        payload,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )


@router.post("/runs/{run_id}/artifacts", response_model=ArtifactRead, status_code=201)
async def create_artifact(
    run_id: uuid.UUID,
    payload: ArtifactWrite,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
) -> ArtifactRead:
    """Create one editable encrypted artifact owned by the Run principal."""

    await _enforce_rate_limit(request, identity)
    return await _artifact_service(session).create(
        run_id,
        payload,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )


@router.get(
    "/conversations/{conversation_id}/artifacts",
    response_model=ArtifactListRead,
)
async def list_artifacts(
    conversation_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ArtifactListRead:
    """Return only the caller's artifacts for one conversation identifier."""

    await _enforce_rate_limit(request, identity)
    artifacts = await _artifact_service(session).list_for_conversation(
        conversation_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        limit=limit,
    )
    return ArtifactListRead(
        conversation_id=conversation_id,
        artifacts=tuple(artifacts),
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactRead)
async def get_artifact(
    artifact_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
) -> ArtifactRead:
    """Return one caller-owned artifact."""

    await _enforce_rate_limit(request, identity)
    return await _artifact_service(session).get(
        artifact_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )


@router.put("/artifacts/{artifact_id}", response_model=ArtifactRead)
async def update_artifact(
    artifact_id: uuid.UUID,
    payload: ArtifactWrite,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
) -> ArtifactRead:
    """Save one artifact only when its revision still matches."""

    await _enforce_rate_limit(request, identity)
    return await _artifact_service(session).update(
        artifact_id,
        payload,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )


@router.delete("/artifacts/{artifact_id}", response_model=ArtifactDeleted)
async def delete_artifact(
    artifact_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: WriteIdentity,
    expected_revision: Annotated[int, Query(ge=1)],
) -> ArtifactDeleted:
    """Delete one artifact only when its revision still matches."""

    await _enforce_rate_limit(request, identity)
    await _artifact_service(session).delete(
        artifact_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        expected_revision=expected_revision,
    )
    return ArtifactDeleted(artifact_id=artifact_id)


@router.get(
    "/runs/{run_id}/feedback",
    response_model=FeedbackStateRead | None,
)
async def get_run_feedback(
    run_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    identity: ReadIdentity,
) -> FeedbackStateRead | None:
    """Return the caller's current feedback value, if any."""

    await _enforce_rate_limit(request, identity)
    return await _feedback_service(session).get(
        run_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )


@router.put("/runs/{run_id}/feedback", response_model=FeedbackStateRead)
async def reconcile_run_feedback(
    run_id: uuid.UUID,
    payload: FeedbackReconcileRequest,
    request: Request,
    session: SessionDependency,
    identity: FeedbackIdentity,
) -> FeedbackStateRead:
    """Reconcile one current value without duplicating same-value signals."""

    await _enforce_rate_limit(request, identity)
    result = await _feedback_service(session).reconcile(
        run_id,
        payload,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )
    request.app.state.evolution_signal_collector.schedule(run_id)
    return result

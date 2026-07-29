"""Owner-scoped Agent Run, replay, answer, artifact, and feedback APIs."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.auth import (
    AuthContext,
    require_chat_read,
    require_chat_write,
    require_feedback_write,
)
from gerclaw_api.dependencies import get_database_session
from gerclaw_api.domain.run_schemas import (
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
    RunEventPage,
)
from gerclaw_api.repositories.agent_run import SqlAlchemyAgentRunRepository
from gerclaw_api.repositories.answer_version import SqlAlchemyAnswerVersionRepository
from gerclaw_api.repositories.run_artifact import SqlAlchemyRunArtifactRepository
from gerclaw_api.repositories.run_feedback import SqlAlchemyRunFeedbackRepository
from gerclaw_api.services.agent_run_service import AgentRunService
from gerclaw_api.services.answer_version_service import AnswerVersionService
from gerclaw_api.services.chat_cancellation import (
    ChatCancellationRegistry,
    ChatCancellationUnavailable,
)
from gerclaw_api.services.rate_limit import RateLimiter
from gerclaw_api.services.run_artifact_service import RunArtifactService
from gerclaw_api.services.run_feedback_service import RunFeedbackService

router = APIRouter(tags=["agent-runs"])
SessionDependency = Annotated[AsyncSession, Depends(get_database_session)]
ReadIdentity = Annotated[AuthContext, Depends(require_chat_read)]
WriteIdentity = Annotated[AuthContext, Depends(require_chat_write)]
FeedbackIdentity = Annotated[AuthContext, Depends(require_feedback_write)]


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
    return await _feedback_service(session).reconcile(
        run_id,
        payload,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )

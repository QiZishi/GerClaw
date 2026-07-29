"""Lease-aware Agent run recovery against real PostgreSQL and Redis."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from gerclaw_api.database.models import AgentRun, RunEvent
from gerclaw_api.domain.run_schemas import AgentRunCreate
from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.repositories.agent_run import SqlAlchemyAgentRunRepository
from gerclaw_api.repositories.conversation import SqlAlchemyConversationRepository
from gerclaw_api.services.agent_run_service import AgentRunService
from gerclaw_api.services.conversation_service import ConversationService
from gerclaw_api.services.run_recovery_service import StaleAgentRunReconciler
from gerclaw_api.services.session_lease import SessionLease

TENANT = "tenant_public0001"
ACTOR = "usr_patient_integration0001"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recovery_interrupts_only_runs_without_cross_replica_lease(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    orphan_session_id = uuid.uuid4()
    active_session_id = uuid.uuid4()
    for session_id in (orphan_session_id, active_session_id):
        response = await client.post(
            "/api/v1/sessions",
            json={"session_id": str(session_id)},
        )
        assert response.status_code == 201, response.text

    async def create_run(session_id: uuid.UUID, trace_id: str, fence: int) -> uuid.UUID:
        async with app.state.database.session() as session:
            conversation_service = ConversationService(
                SqlAlchemyConversationRepository(session)
            )
            conversation = await conversation_service.require_session(
                session_id,
                tenant_id=TENANT,
                actor_id=ACTOR,
            )
            message = await conversation_service.store_user_message(
                tenant_id=TENANT,
                conversation=conversation,
                session_id=session_id,
                trace_id=trace_id,
                text="恢复测试",
                channel="web",
            )
            run = await AgentRunService(
                SqlAlchemyAgentRunRepository(session)
            ).create_run(
                AgentRunCreate(
                    conversation_id=session_id,
                    input_message_id=message.id,
                    trace_id=trace_id,
                    route=RouteKind.STANDARD,
                    fencing_token=fence,
                ),
                tenant_id=TENANT,
                actor_id=ACTOR,
            )
            return run.id

    orphan_run_id = await create_run(
        orphan_session_id,
        "trace_recovery_orphan_0001",
        101,
    )
    active_run_id = await create_run(
        active_session_id,
        "trace_recovery_active_0001",
        102,
    )
    active_lease_key = SessionLease.key_for(
        tenant_id=TENANT,
        session_id=active_session_id,
    )
    await app.state.redis.set(active_lease_key, "102:other-replica", ex=60)
    try:
        interrupted_count = await StaleAgentRunReconciler(
            app.state.database,
            app.state.redis,
            batch_size=1,
        ).reconcile()
    finally:
        await app.state.redis.delete(active_lease_key)

    async with app.state.database.session() as session:
        orphan = await session.get(AgentRun, orphan_run_id)
        active = await session.get(AgentRun, active_run_id)
        orphan_events = list(
            (
                await session.scalars(
                    select(RunEvent).where(RunEvent.run_id == orphan_run_id)
                )
            ).all()
        )
    assert interrupted_count == 1
    assert orphan is not None and orphan.status == "interrupted"
    assert orphan.completed_at is not None
    assert active is not None and active.status == "running"
    assert [event.status for event in orphan_events] == ["interrupted"]

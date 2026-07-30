"""Real PostgreSQL races for the execution-time directive ledger."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text

from gerclaw_api.database.models import RunDirective
from gerclaw_api.domain.run_schemas import (
    AgentRunCreate,
    RunDirectiveClaim,
    RunDirectiveCreate,
    RunDirectiveMode,
    RunDirectiveStatus,
)
from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.repositories.agent_run import SqlAlchemyAgentRunRepository
from gerclaw_api.repositories.conversation import SqlAlchemyConversationRepository
from gerclaw_api.repositories.run_directive import SqlAlchemyRunDirectiveRepository
from gerclaw_api.services.agent_run_service import AgentRunService
from gerclaw_api.services.conversation_service import ConversationService
from gerclaw_api.services.run_directive_service import (
    RunDirectiveConflictError,
    RunDirectiveService,
)

TENANT = "tenant_public0001"
ACTOR = "usr_patient_integration0001"


async def _create_run(client: AsyncClient, app: object) -> tuple[uuid.UUID, int]:
    conversation_id = uuid.uuid4()
    response = await client.post(
        "/api/v1/sessions",
        json={"session_id": str(conversation_id)},
    )
    assert response.status_code == 201, response.text
    async with app.state.database.session() as session:  # type: ignore[attr-defined]
        conversations = ConversationService(SqlAlchemyConversationRepository(session))
        conversation = await conversations.require_session(
            conversation_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        message = await conversations.store_user_message(
            tenant_id=TENANT,
            conversation=conversation,
            session_id=conversation_id,
            trace_id="trace_directive_integration_0001",
            text="请开始整理用药信息。",
            channel="web",
        )
        run = await AgentRunService(SqlAlchemyAgentRunRepository(session)).create_run(
            AgentRunCreate(
                conversation_id=conversation_id,
                input_message_id=message.id,
                trace_id="trace_directive_integration_0001",
                route=RouteKind.STANDARD,
                fencing_token=41,
            ),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    return run.id, 41


@pytest.mark.integration
@pytest.mark.asyncio
async def test_same_idempotency_key_converges_and_claim_is_fenced(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    run_id, fence = await _create_run(client, app)
    request = RunDirectiveCreate(
        mode=RunDirectiveMode.QUEUE_FOR_NEXT_BOUNDARY,
        instruction="下一步先结合最新化验结果。",
        idempotency_key="directive-integration-same-key",
    )

    async def create_once() -> uuid.UUID:
        async with app.state.database.session() as session:
            result = await RunDirectiveService(
                SqlAlchemyRunDirectiveRepository(session)
            ).create(
                run_id,
                request.model_copy(update={"id": uuid.uuid4()}),
                tenant_id=TENANT,
                actor_id=ACTOR,
            )
            return result.id

    identities = await asyncio.gather(*(create_once() for _ in range(10)))

    assert len(set(identities)) == 1
    async with app.state.database.session() as session:
        assert await session.scalar(select(func.count()).select_from(RunDirective)) == 1
        encrypted_value = await session.scalar(
            text(
                "SELECT instruction FROM run_directives "
                "WHERE id = CAST(:directive_id AS uuid)"
            ),
            {"directive_id": str(identities[0])},
        )
        assert isinstance(encrypted_value, str)
        assert request.instruction not in encrypted_value

    claim = RunDirectiveClaim(fencing_token=fence, boundary_id="before-model-integration")
    async with app.state.database.session() as session:
        claimed = await RunDirectiveService(
            SqlAlchemyRunDirectiveRepository(session)
        ).claim_next(
            run_id,
            claim,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    assert claimed is not None
    assert claimed.status is RunDirectiveStatus.CLAIMED

    async with app.state.database.session() as session:
        with pytest.raises(RunDirectiveConflictError):
            await RunDirectiveService(
                SqlAlchemyRunDirectiveRepository(session)
            ).mark_applied(
                claimed.id,
                claim.model_copy(update={"fencing_token": fence + 1}),
                tenant_id=TENANT,
                actor_id=ACTOR,
            )

    async with app.state.database.session() as session:
        applied = await RunDirectiveService(
            SqlAlchemyRunDirectiveRepository(session)
        ).mark_applied(
            claimed.id,
            claim,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    assert applied.status is RunDirectiveStatus.APPLIED

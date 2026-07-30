"""Real PostgreSQL races for the execution-time directive ledger."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text

from gerclaw_api.auth import create_access_token
from gerclaw_api.database.models import Message, RunDirective
from gerclaw_api.domain.run_schemas import (
    AgentRunCreate,
    AgentRunRead,
    AgentRunStatus,
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


async def _create_run(client: AsyncClient, app: object) -> tuple[uuid.UUID, int, str]:
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
    return run.id, 41, run.trace_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_same_idempotency_key_converges_and_claim_is_fenced(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    run_id, fence, _trace_id = await _create_run(client, app)
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_queue_api_lists_and_withdraws_unclaimed_instruction(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    run_id, _fence, trace_id = await _create_run(client, app)

    queued = await client.post(
        f"/api/v1/chat/{trace_id}/directives/queue",
        json={
            "instruction": "下一步先解释检查指标。",
            "idempotency_key": "directive-api-queue-1",
        },
    )
    assert queued.status_code == 201, queued.text
    directive = queued.json()
    assert directive["target_run_id"] == str(run_id)
    assert directive["mode"] == "queue_for_next_boundary"
    assert directive["status"] == "pending"
    assert "claimed_by_fencing_token" not in directive
    assert "claim_boundary_id" not in directive
    assert "idempotency_key" not in directive

    queued_second = await client.post(
        f"/api/v1/chat/{trace_id}/directives/queue",
        json={
            "instruction": "然后保留尚未处理的复查要求。",
            "idempotency_key": "directive-api-queue-2",
        },
    )
    assert queued_second.status_code == 201, queued_second.text

    claim = RunDirectiveClaim(fencing_token=41, boundary_id="before-terminal-race")
    async with app.state.database.session() as session:
        claimed = await RunDirectiveService(
            SqlAlchemyRunDirectiveRepository(session)
        ).claim_next(
            run_id,
            claim,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    assert claimed is not None and str(claimed.id) == directive["id"]

    listed = await client.get(f"/api/v1/runs/{run_id}/directives")
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["directives"]] == [
        directive["id"],
        queued_second.json()["id"],
    ]

    async with app.state.database.session() as session:
        runs = AgentRunService(SqlAlchemyAgentRunRepository(session))
        current = await runs.get_run(run_id, tenant_id=TENANT, actor_id=ACTOR)
        await runs.transition(
            run_id,
            AgentRunStatus.COMPLETED,
            tenant_id=TENANT,
            actor_id=ACTOR,
            expected_revision=current.revision,
            fencing_token=41,
        )
    deferred = await client.get(f"/api/v1/runs/{run_id}/directives")
    assert deferred.status_code == 200, deferred.text
    assert [item["status"] for item in deferred.json()["directives"]] == [
        "pending_next_run",
        "pending_next_run",
    ]

    async with app.state.database.session() as session:
        with pytest.raises(RunDirectiveConflictError):
            await RunDirectiveService(
                SqlAlchemyRunDirectiveRepository(session)
            ).mark_applied(
                claimed.id,
                claim,
                tenant_id=TENANT,
                actor_id=ACTOR,
            )

    withdrawn = await client.delete(f"/api/v1/run-directives/{directive['id']}")
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "cancelled"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_directive_apis_hide_trace_run_and_directive_across_principals(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    run_id, _fence, trace_id = await _create_run(client, app)
    queued = await client.post(
        f"/api/v1/chat/{trace_id}/directives/queue",
        json={
            "instruction": "只属于原始主体的要求。",
            "idempotency_key": "directive-api-owner-isolation",
        },
    )
    assert queued.status_code == 201, queued.text
    directive_id = queued.json()["id"]
    foreign_principals = (
        ("tenant_public0001", "usr_patient_integration_other"),
        ("tenant_public_other", ACTOR),
    )
    for tenant_id, actor_id in foreign_principals:
        token = create_access_token(
            app.state.settings,
            actor_id=actor_id,
            tenant_id=tenant_id,
            scopes={"chat:read", "chat:write"},
            role="patient",
            account_role="patient",
        )
        headers = {"Authorization": f"Bearer {token}"}
        hidden_queue = await client.post(
            f"/api/v1/chat/{trace_id}/directives/queue",
            headers=headers,
            json={
                "instruction": "不得通过 Trace 探测其他主体。",
                "idempotency_key": f"foreign-{tenant_id}-{actor_id}",
            },
        )
        hidden_list = await client.get(
            f"/api/v1/runs/{run_id}/directives",
            headers=headers,
        )
        hidden_cancel = await client.delete(
            f"/api/v1/run-directives/{directive_id}",
            headers=headers,
        )
        assert hidden_queue.status_code == 404
        assert hidden_list.status_code == 404
        assert hidden_cancel.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_terminal_queued_directive_binds_and_applies_on_next_run(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    original_run_id, fence, trace_id = await _create_run(client, app)
    async with app.state.database.session() as session:
        runs = AgentRunService(SqlAlchemyAgentRunRepository(session))
        original = await runs.get_run(
            original_run_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        await runs.transition(
            original_run_id,
            AgentRunStatus.COMPLETED,
            tenant_id=TENANT,
            actor_id=ACTOR,
            expected_revision=original.revision,
            fencing_token=fence,
        )

    queued = await client.post(
        f"/api/v1/chat/{trace_id}/directives/queue",
        json={
            "instruction": "下一轮先核对最近三天持续头晕。",
            "idempotency_key": "directive-terminal-next-run",
        },
    )
    assert queued.status_code == 201, queued.text
    assert queued.json()["status"] == RunDirectiveStatus.PENDING_NEXT_RUN.value
    directive_id = uuid.UUID(queued.json()["id"])

    successor_trace_id = "trace_directive_integration_successor_0001"
    successor_fence = fence + 1
    async with app.state.database.session() as session:
        conversations = ConversationService(SqlAlchemyConversationRepository(session))
        original = await AgentRunService(
            SqlAlchemyAgentRunRepository(session)
        ).get_run(
            original_run_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        conversation = await conversations.claim_fencing_token(
            original.conversation_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=successor_fence,
            trace_id=successor_trace_id,
        )
        message = await conversations.store_user_message(
            tenant_id=TENANT,
            conversation=conversation,
            session_id=original.conversation_id,
            trace_id=successor_trace_id,
            text="请继续处理。",
            channel="web",
        )
    async with app.state.database.session() as session:
        successor = await AgentRunService(
            SqlAlchemyAgentRunRepository(session)
        ).create_run(
            AgentRunCreate(
                conversation_id=original.conversation_id,
                input_message_id=message.id,
                trace_id=successor_trace_id,
                route=RouteKind.STANDARD,
                fencing_token=successor_fence,
            ),
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    claim = RunDirectiveClaim(
        fencing_token=successor_fence,
        boundary_id="before-model-successor",
    )
    async with app.state.database.session() as session:
        directives = RunDirectiveService(SqlAlchemyRunDirectiveRepository(session))
        claimed = await directives.claim_next(
            successor.id,
            claim,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        assert claimed is not None and claimed.id == directive_id
        applied = await directives.mark_applied(
            directive_id,
            claim,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    assert applied.status is RunDirectiveStatus.APPLIED
    assert applied.successor_run_id == successor.id
    async with app.state.database.session() as session:
        projected_count = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.trace_id == f"directive_{directive_id.hex}")
        )
    assert projected_count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_terminal_and_successor_creation_race_still_binds_directive(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    original_run_id, fence, trace_id = await _create_run(client, app)
    queued = await client.post(
        f"/api/v1/chat/{trace_id}/directives/queue",
        json={
            "instruction": "竞态后仍在下一轮核对用药。",
            "idempotency_key": "directive-successor-binding-race",
        },
    )
    assert queued.status_code == 201, queued.text
    directive_id = uuid.UUID(queued.json()["id"])
    successor_trace_id = "trace_directive_successor_race_0001"
    successor_fence = fence + 1
    async with app.state.database.session() as session:
        runs = AgentRunService(SqlAlchemyAgentRunRepository(session))
        original = await runs.get_run(
            original_run_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        original_revision = original.revision
        conversation_id = original.conversation_id
        conversations = ConversationService(SqlAlchemyConversationRepository(session))
        conversation = await conversations.claim_fencing_token(
            conversation_id,
            tenant_id=TENANT,
            actor_id=ACTOR,
            fencing_token=successor_fence,
            trace_id=successor_trace_id,
        )
        message = await conversations.store_user_message(
            tenant_id=TENANT,
            conversation=conversation,
            session_id=conversation_id,
            trace_id=successor_trace_id,
            text="开始下一轮。",
            channel="web",
        )
        successor_message_id = message.id

    async def complete_original() -> object:
        async with app.state.database.session() as session:
            return await AgentRunService(
                SqlAlchemyAgentRunRepository(session)
            ).transition(
                original_run_id,
                AgentRunStatus.COMPLETED,
                tenant_id=TENANT,
                actor_id=ACTOR,
                expected_revision=original_revision,
                fencing_token=fence,
            )

    async def create_successor() -> object:
        async with app.state.database.session() as session:
            return await AgentRunService(
                SqlAlchemyAgentRunRepository(session)
            ).create_run(
                AgentRunCreate(
                    conversation_id=conversation_id,
                    input_message_id=successor_message_id,
                    trace_id=successor_trace_id,
                    route=RouteKind.STANDARD,
                    fencing_token=successor_fence,
                ),
                tenant_id=TENANT,
                actor_id=ACTOR,
            )

    completed, successor_value = await asyncio.gather(
        complete_original(),
        create_successor(),
    )
    assert completed is not None
    successor_id = cast(AgentRunRead, successor_value).id
    claim = RunDirectiveClaim(
        fencing_token=successor_fence,
        boundary_id="before-model-race-successor",
    )
    async with app.state.database.session() as session:
        directives = RunDirectiveService(SqlAlchemyRunDirectiveRepository(session))
        claimed = await directives.claim_next(
            successor_id,
            claim,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
        assert claimed is not None and claimed.id == directive_id
        applied = await directives.mark_applied(
            directive_id,
            claim,
            tenant_id=TENANT,
            actor_id=ACTOR,
        )
    assert applied.successor_run_id == successor_id
    assert applied.status is RunDirectiveStatus.APPLIED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_terminal_and_batch_apply_race_has_one_consistent_outcome(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    run_id, fence, trace_id = await _create_run(client, app)
    queued = await client.post(
        f"/api/v1/chat/{trace_id}/directives/queue",
        json={
            "instruction": "竞态中仍只应用一次。",
            "idempotency_key": "directive-terminal-apply-race",
        },
    )
    directive_id = uuid.UUID(queued.json()["id"])
    claim = RunDirectiveClaim(fencing_token=fence, boundary_id="race-boundary")
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

    async def complete() -> object:
        async with app.state.database.session() as session:
            service = AgentRunService(SqlAlchemyAgentRunRepository(session))
            run = await service.get_run(run_id, tenant_id=TENANT, actor_id=ACTOR)
            return await service.transition(
                run_id,
                AgentRunStatus.COMPLETED,
                tenant_id=TENANT,
                actor_id=ACTOR,
                expected_revision=run.revision,
                fencing_token=fence,
            )

    async def apply() -> object:
        async with app.state.database.session() as session:
            return await RunDirectiveService(
                SqlAlchemyRunDirectiveRepository(session)
            ).mark_many_applied(
                run_id,
                (directive_id,),
                claim,
                tenant_id=TENANT,
                actor_id=ACTOR,
            )

    outcomes = await asyncio.gather(complete(), apply(), return_exceptions=True)
    assert sum(not isinstance(item, BaseException) for item in outcomes) >= 1
    async with app.state.database.session() as session:
        directive = await session.get(RunDirective, directive_id)
        assert directive is not None
        assert directive.status in {
            RunDirectiveStatus.APPLIED.value,
            RunDirectiveStatus.PENDING_NEXT_RUN.value,
        }
        projected_count = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.trace_id == f"directive_{directive_id.hex}")
        )
        assert projected_count == (
            1 if directive.status == RunDirectiveStatus.APPLIED.value else 0
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_terminal_and_withdraw_race_never_revives_cancelled_directive(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    run_id, fence, trace_id = await _create_run(client, app)
    queued = await client.post(
        f"/api/v1/chat/{trace_id}/directives/queue",
        json={
            "instruction": "这条要求会在竞态中撤销。",
            "idempotency_key": "directive-terminal-cancel-race",
        },
    )
    directive_id = uuid.UUID(queued.json()["id"])

    async def complete() -> object:
        async with app.state.database.session() as session:
            service = AgentRunService(SqlAlchemyAgentRunRepository(session))
            run = await service.get_run(run_id, tenant_id=TENANT, actor_id=ACTOR)
            return await service.transition(
                run_id,
                AgentRunStatus.COMPLETED,
                tenant_id=TENANT,
                actor_id=ACTOR,
                expected_revision=run.revision,
                fencing_token=fence,
            )

    async def withdraw() -> object:
        async with app.state.database.session() as session:
            return await RunDirectiveService(
                SqlAlchemyRunDirectiveRepository(session)
            ).cancel_unclaimed(
                directive_id,
                tenant_id=TENANT,
                actor_id=ACTOR,
            )

    await asyncio.gather(complete(), withdraw())
    async with app.state.database.session() as session:
        directive = await session.get(RunDirective, directive_id)
        assert directive is not None
        assert directive.status == RunDirectiveStatus.CANCELLED.value

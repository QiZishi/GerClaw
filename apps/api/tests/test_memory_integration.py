"""Encrypted PostgreSQL and PHI-free Qdrant Memory integration tests."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from gerclaw_api.auth import create_access_token
from gerclaw_api.modules.memory.compressor import AgentScopeContextCompressor
from gerclaw_api.modules.memory.memory_module import ProductionMemoryModule
from gerclaw_api.modules.memory.models import ExtractedMemoryFact, MemoryFactDetails
from gerclaw_api.modules.memory.protocols import MemoryMessage
from gerclaw_api.modules.memory.store import memory_point_id
from gerclaw_api.repositories.memory import SqlAlchemyMemoryRepository

TENANT = "tenant_public0001"
ACTOR = "usr_patient_integration0001"


class _EvidencedExtractor:
    async def extract(self, text_value: str) -> list[tuple[ExtractedMemoryFact, str]]:
        assert "青霉素" in text_value
        return [
            (
                ExtractedMemoryFact(
                    category="allergy",
                    memory_type="stable",
                    entity="青霉素",
                    statement="用户自述对青霉素过敏",
                    evidence_span="对青霉素过敏",
                    confidence=0.99,
                    details=MemoryFactDetails(reaction="皮疹"),
                ),
                "confirmed",
            )
        ]


class _DeterministicEmbedding:
    async def __call__(self, inputs: list[str]) -> Any:
        return SimpleNamespace(embeddings=[[1.0] * 1024 for _ in inputs])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_profile_is_encrypted_actor_scoped_and_phi_free_in_qdrant(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, app = integration_client
    session_id = uuid.uuid4()
    created = await client.post("/api/v1/sessions", json={"session_id": str(session_id)})
    assert created.status_code == 201, created.text

    async with app.state.database.session() as database_session:
        repository = SqlAlchemyMemoryRepository(database_session)
        user = await repository.get_user(tenant_id=TENANT, actor_id=ACTOR)
        assert user is not None
        module = ProductionMemoryModule(
            repository=repository,
            extractor=cast(Any, _EvidencedExtractor()),
            compressor=AgentScopeContextCompressor(app.state.agent_model),
            embedding_model=cast(Any, _DeterministicEmbedding()),
            vector_store=app.state.memory_store,
            namespace_secret=app.state.settings.auth_jwt_secret.get_secret_value().encode(),
            tenant_id=TENANT,
            actor_id=ACTOR,
            user_id=user.id,
            session_id=session_id,
            trace_id="trace_memory_integration0001",
            retrieval_top_k=5,
            retrieval_candidates=20,
        )
        await module.extract_and_update_profile(
            ACTOR,
            [
                MemoryMessage(
                    role="user",
                    content=[{"type": "text", "text": "我明确对青霉素过敏, 曾出现皮疹"}],
                )
            ],
        )
        fact_id = module.last_update.changed_fact_ids[0]
        await module.commit()

    profile = await client.get("/api/v1/memory/profile")
    assert profile.status_code == 200, profile.text
    payload = profile.json()
    assert payload["version"] == 2
    assert payload["facts"][0]["statement"] == "用户自述: 对青霉素过敏"
    assert payload["facts"][0]["status"] == "proposed"
    assert payload["profile"]["allergies"] == []
    assert payload["profile"]["pending_items"][0]["details"]["evidence_span"] == "对青霉素过敏"

    confirmed = await client.post(
        f"/api/v1/memory/facts/{fact_id}/decision",
        json={"expected_revision": 1, "decision": "confirm"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["fact"]["status"] == "confirmed"
    assert confirmed.json()["fact"]["revision"] == 2

    profile = await client.get("/api/v1/memory/profile")
    assert profile.status_code == 200, profile.text
    assert profile.json()["profile"]["allergies"][0]["details"]["evidence_span"] == "对青霉素过敏"

    async with app.state.database.engine.connect() as connection:
        raw_fact = (
            await connection.execute(
                text(
                    "SELECT statement, details FROM memory_facts "
                    "WHERE tenant_id=:tenant AND id=:fact_id"
                ),
                {"tenant": TENANT, "fact_id": fact_id},
            )
        ).one()
        raw_profile = (
            await connection.execute(
                text("SELECT profile FROM health_profiles WHERE tenant_id=:tenant"),
                {"tenant": TENANT},
            )
        ).scalar_one()
    assert raw_fact.statement.startswith("enc:v1:")
    assert raw_fact.details.startswith("enc:v1:")
    assert raw_profile.startswith("enc:v1:")
    assert "青霉素" not in raw_fact.statement + raw_fact.details + raw_profile

    points = await app.state.qdrant.retrieve(
        collection_name=app.state.settings.memory_collection_name,
        ids=[memory_point_id(fact_id, 2)],
        with_payload=True,
        with_vectors=False,
    )
    assert len(points) == 1
    qdrant_payload = points[0].payload or {}
    assert set(qdrant_payload) == {
        "tenant_namespace",
        "user_namespace",
        "fact_id",
        "category",
        "status",
        "revision",
    }
    assert "青霉素" not in repr(qdrant_payload)
    assert TENANT not in repr(qdrant_payload)

    deleted = await client.request(
        "DELETE",
        f"/api/v1/memory/facts/{fact_id}",
        json={"expected_revision": 2, "reason": "incorrect"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["fact"]["status"] == "inactive"
    assert deleted.json()["fact"]["revision"] == 3
    assert deleted.json()["fact"]["tombstone_reason"] == "incorrect"
    assert deleted.json()["fact"]["can_restore"] is True

    async with app.state.database.engine.connect() as connection:
        raw_revisions = (
            await connection.execute(
                text(
                    "SELECT revision, activity, snapshot FROM memory_fact_revisions "
                    "WHERE tenant_id=:tenant AND fact_id=:fact_id ORDER BY revision"
                ),
                {"tenant": TENANT, "fact_id": fact_id},
            )
        ).all()
    assert [(row.revision, row.activity) for row in raw_revisions] == [
        (1, "user_decision"),
        (2, "user_delete"),
    ]
    assert all(row.snapshot.startswith("enc:v1:") for row in raw_revisions)
    assert all("青霉素" not in row.snapshot for row in raw_revisions)

    history = await client.get(f"/api/v1/memory/facts/{fact_id}/history")
    assert history.status_code == 200, history.text
    history_payload = history.json()
    assert history_payload["fact_id"] == str(fact_id)
    assert len(history_payload["items"]) == 2
    history_item = history_payload["items"][0]
    assert history_item["revision"] == 2
    assert history_item["activity"] == "user_delete"
    assert history_item["category"] == "allergy"
    assert history_item["memory_type"] == "stable"
    assert history_item["status"] == "confirmed"
    assert history_item["statement"] == "用户自述: 对青霉素过敏"
    assert {
        key: history_item["details"][key] for key in ("evidence_span", "reaction", "source_status")
    } == {
        "evidence_span": "对青霉素过敏",
        "reaction": "皮疹",
        "source_status": "unknown",
    }
    assert history_item["confidence"] == 0.99
    assert history_item["source_trace_id"] == "trace_memory_integration0001"
    assert history_item["occurred_at"] is None
    assert history_item["confirmed_at"] is not None
    assert history_item["updated_at"] is not None
    assert history_item["recorded_at"] is not None

    restored = await client.post(
        f"/api/v1/memory/facts/{fact_id}/restore",
        json={"expected_revision": 3},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["fact"]["status"] == "confirmed"
    assert restored.json()["fact"]["revision"] == 4
    assert restored.json()["fact"]["can_restore"] is False

    created_fact = await client.post(
        "/api/v1/memory/facts",
        json={
            "expected_profile_version": restored.json()["profile_version"],
            "category": "goal",
            "memory_type": "evolving",
            "entity": "每日步行",
            "statement": "我的每日步行目标是3000步",
            "details": {"value": "3000", "unit": "步"},
        },
    )
    assert created_fact.status_code == 201, created_fact.text
    assert created_fact.json()["fact"]["status"] == "proposed"
    goal_id = created_fact.json()["fact"]["id"]

    evidence_mismatch = await client.patch(
        f"/api/v1/memory/facts/{goal_id}",
        json={
            "expected_revision": 1,
            "statement": "我的每日步行目标是4000步",
            "details": {"value": "9000", "unit": "步"},
        },
    )
    assert evidence_mismatch.status_code == 422, evidence_mismatch.text
    assert evidence_mismatch.json()["detail"]["code"] == "MEMORY_EVIDENCE_MISMATCH"

    updated_fact = await client.patch(
        f"/api/v1/memory/facts/{goal_id}",
        json={
            "expected_revision": 1,
            "statement": "我的每日步行目标是4000步",
            "details": {"value": "4000", "unit": "步"},
        },
    )
    assert updated_fact.status_code == 200, updated_fact.text
    assert updated_fact.json()["fact"]["revision"] == 2
    assert updated_fact.json()["fact"]["statement"] == "我的每日步行目标是4000步"

    other_token = create_access_token(
        app.state.settings,
        actor_id="usr_patient_integration0002",
        tenant_id=TENANT,
        scopes={"memory:read", "memory:write"},
        role="patient",
        account_role="patient",
    )
    hidden = await client.get(
        "/api/v1/memory/profile",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert hidden.status_code == 200
    assert hidden.json()["version"] == 0
    assert hidden.json()["facts"] == []
    forbidden_delete = await client.request(
        "DELETE",
        f"/api/v1/memory/facts/{fact_id}",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"expected_revision": 4, "reason": "user_deleted"},
    )
    assert forbidden_delete.status_code == 404
    forbidden_history = await client.get(
        f"/api/v1/memory/facts/{fact_id}/history",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert forbidden_history.status_code == 404

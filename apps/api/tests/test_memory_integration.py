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
    assert payload["facts"][0]["statement"] == "用户自述对青霉素过敏"
    assert payload["profile"]["allergies"][0]["details"]["evidence_span"] == "对青霉素过敏"

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
        ids=[memory_point_id(fact_id, 1)],
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

    rejected = await client.post(
        f"/api/v1/memory/facts/{fact_id}/decision",
        json={"expected_revision": 1, "decision": "reject"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["fact"]["status"] == "inactive"
    assert rejected.json()["fact"]["revision"] == 2

    other_token = create_access_token(
        app.state.settings,
        actor_id="usr_patient_integration0002",
        tenant_id=TENANT,
        scopes={"memory:read", "memory:write"},
    )
    hidden = await client.get(
        "/api/v1/memory/profile",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert hidden.status_code == 200
    assert hidden.json()["version"] == 0
    assert hidden.json()["facts"] == []
    forbidden_decision = await client.post(
        f"/api/v1/memory/facts/{fact_id}/decision",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"expected_revision": 2, "decision": "confirm"},
    )
    assert forbidden_decision.status_code == 404

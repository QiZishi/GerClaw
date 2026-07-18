"""Shared test settings and real-dependency fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from gerclaw_api.application import create_app
from gerclaw_api.auth import create_access_token
from gerclaw_api.config import Settings

TEST_JWT_SECRET = "tests-only-jwt-secret-that-is-longer-than-32-characters"
TEST_GUEST_IDENTITY_SECRET = "tests-only-guest-identity-secret-longer-than-32-characters"
TEST_DATA_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def make_settings(**overrides: object) -> Settings:
    """Build deterministic settings without consulting process defaults."""

    values: dict[str, object] = {
        "app_env": "test",
        "database_url": "postgresql+asyncpg://gerclaw:change-me@127.0.0.1:5432/gerclaw",
        "redis_url": "redis://:local-redis-only@127.0.0.1:6379/15",
        "qdrant_url": "http://127.0.0.1:6333",
        "qdrant_api_key": "local-qdrant-only",
        "knowledge_base_path": Path(__file__).parent,
        "siliconflow_url": "http://127.0.0.1:9/v1",
        "siliconflow_api_key": "tests-only-siliconflow-key",
        "embedding_model": "BAAI/bge-m3",
        "rerank_model": "BAAI/bge-reranker-v2-m3",
        "anysearch_url": "http://127.0.0.1:9",
        "anysearch_api_key": "tests-only-anysearch-key",
        "tavily_url": "http://127.0.0.1:9",
        "tavily_api_key": "tests-only-tavily-key",
        "cors_origins": ["http://localhost:3000"],
        "readiness_cache_seconds": 0,
        "auth_jwt_secret": TEST_JWT_SECRET,
        "guest_identity_secret": TEST_GUEST_IDENTITY_SECRET,
        "data_encryption_key": TEST_DATA_KEY,
        "data_encryption_key_id": "test-v1",
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.fixture
def unit_settings() -> Settings:
    """Deterministic settings for pure unit tests."""

    return make_settings()


@pytest.fixture
def integration_settings() -> Settings:
    """Return settings for explicitly enabled real-dependency tests."""

    if os.getenv("GERCLAW_RUN_INTEGRATION") != "1":
        pytest.skip("set GERCLAW_RUN_INTEGRATION=1 to run real dependency tests")
    database_url = os.getenv(
        "GERCLAW_TEST_DATABASE_URL",
        "postgresql+asyncpg://gerclaw:local-postgres-only@127.0.0.1:5432/gerclaw_test",
    )
    if not (make_url(database_url).database or "").endswith("_test"):
        raise pytest.UsageError("GERCLAW_TEST_DATABASE_URL must name a dedicated *_test database")
    knowledge_base_path = os.getenv("GERCLAW_TEST_KNOWLEDGE_BASE_PATH")
    if knowledge_base_path is None:
        raise pytest.UsageError(
            "GERCLAW_TEST_KNOWLEDGE_BASE_PATH must explicitly name the real test corpus"
        )
    real_services = Settings()
    if any(
        value is None
        for value in (
            real_services.siliconflow_url,
            real_services.siliconflow_api_key,
            real_services.embedding_model,
            real_services.rerank_model,
        )
    ):
        raise pytest.UsageError("root .env must configure the real RAG model services")
    if len(real_services.agent_model_configs) != 3:
        raise pytest.UsageError("root .env must configure all three Agent model services")
    return make_settings(
        database_url=database_url,
        redis_url=os.getenv(
            "GERCLAW_TEST_REDIS_URL", "redis://:local-redis-only@127.0.0.1:6379/15"
        ),
        qdrant_url=os.getenv("GERCLAW_TEST_QDRANT_URL", "http://127.0.0.1:6333"),
        qdrant_api_key=os.getenv("GERCLAW_TEST_QDRANT_API_KEY", "local-qdrant-only"),
        memory_collection_name=os.getenv(
            "GERCLAW_TEST_MEMORY_COLLECTION_NAME", "gerclaw_user_memory_test_v1"
        ),
        knowledge_base_path=Path(knowledge_base_path),
        siliconflow_url=real_services.siliconflow_url,
        siliconflow_api_key=real_services.siliconflow_api_key.get_secret_value(),
        embedding_model=real_services.embedding_model,
        rerank_model=real_services.rerank_model,
        anysearch_url=real_services.anysearch_url,
        anysearch_api_key=(
            real_services.anysearch_api_key.get_secret_value()
            if real_services.anysearch_api_key is not None
            else None
        ),
        tavily_url=real_services.tavily_url,
        tavily_api_key=(
            real_services.tavily_api_key.get_secret_value()
            if real_services.tavily_api_key is not None
            else None
        ),
        agent_primary_url=real_services.agent_primary_url,
        agent_primary_api_key=real_services.agent_primary_api_key.get_secret_value()
        if real_services.agent_primary_api_key is not None
        else None,
        agent_primary_model=real_services.agent_primary_model,
        agent_primary_protocol=real_services.agent_primary_protocol,
        agent_backup1_url=real_services.agent_backup1_url,
        agent_backup1_api_key=real_services.agent_backup1_api_key.get_secret_value()
        if real_services.agent_backup1_api_key is not None
        else None,
        agent_backup1_model=real_services.agent_backup1_model,
        agent_backup1_protocol=real_services.agent_backup1_protocol,
        agent_backup2_url=real_services.agent_backup2_url,
        agent_backup2_api_key=real_services.agent_backup2_api_key.get_secret_value()
        if real_services.agent_backup2_api_key is not None
        else None,
        agent_backup2_model=real_services.agent_backup2_model,
        agent_backup2_protocol=real_services.agent_backup2_protocol,
    )


@pytest.fixture
async def integration_client(
    integration_settings: Settings,
) -> AsyncIterator[tuple[AsyncClient, object]]:
    """Start the full application and truncate mutable tables around each test."""

    app = create_app(integration_settings)
    async with app.router.lifespan_context(app):
        await app.state.redis.flushdb()
        if await app.state.qdrant.collection_exists(integration_settings.memory_collection_name):
            await app.state.qdrant.delete_collection(integration_settings.memory_collection_name)
        async with app.state.database.engine.begin() as connection:
            await connection.execute(
                text(
                    "TRUNCATE provider_egress_events, runtime_checkpoints, runtime_approvals, "
                    "prescription_draft_reviews, patient_access_grants, "
                    "bad_cases, user_feedback, "
                    "trace_events, messages, "
                    "skill_definition_revisions, session_skills, skill_definitions, "
                    "memory_fact_revisions, memory_facts, health_profiles, sessions, users, "
                    "execution_traces "
                    "RESTART IDENTITY CASCADE"
                )
            )
        token = create_access_token(
            integration_settings,
            actor_id="usr_patient_integration0001",
            tenant_id="tenant_public0001",
            scopes={
                "approval:read",
                "approval:write",
                "trace:read",
                "trace:write",
                "feedback:write",
                "metrics:read",
                "rag:read",
                "chat:read",
                "chat:write",
                "memory:read",
                "memory:write",
                "search:read",
                "skill:read",
                "skill:write",
                "skill:execute",
            },
            role="patient",
            account_role="patient",
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client, app
        if await app.state.qdrant.collection_exists(integration_settings.memory_collection_name):
            await app.state.qdrant.delete_collection(integration_settings.memory_collection_name)

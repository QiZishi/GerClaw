"""Memory protocol and production runtime must match design requirement §4.8."""

import uuid
from typing import Any, cast

from qdrant_client import AsyncQdrantClient

from gerclaw_api.modules.memory.memory_module import ProductionMemoryModule
from gerclaw_api.modules.memory.protocols import MemoryModule
from gerclaw_api.modules.memory.runtime import create_memory_module, create_memory_store
from tests.conftest import make_settings


def test_memory_exposes_all_required_lifecycle_methods() -> None:
    for name in (
        "get_short_term",
        "get_long_term",
        "save_message",
        "extract_and_update_profile",
        "compress_context",
    ):
        assert hasattr(MemoryModule, name)


def test_memory_runtime_builds_isolated_store_and_turn_module() -> None:
    settings = make_settings()
    client = AsyncQdrantClient(location=":memory:")
    store = create_memory_store(settings, client)

    module = create_memory_module(
        settings=settings,
        repository=cast(Any, object()),
        model=cast(Any, object()),
        embedding_model=cast(Any, object()),
        vector_store=store,
        tenant_id="tenant_memory0001",
        actor_id="usr_memory_contract0001",
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        trace_id="trace_memory_contract0001",
    )

    assert store.collection == settings.memory_collection_name
    assert isinstance(module, ProductionMemoryModule)

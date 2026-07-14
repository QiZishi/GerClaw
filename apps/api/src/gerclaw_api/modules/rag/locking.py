"""Cross-process serialization for destructive RAG index reconciliation."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

LOGGER = logging.getLogger(__name__)
_RAG_INDEX_ADVISORY_LOCK_ID = 2_026_071_500_15


class RAGIndexLock(Protocol):
    """Serialize every operation that can mutate the shared RAG collection."""

    def hold(self) -> AbstractAsyncContextManager[str]:
        """Wait for ownership and yield a unique generation-fencing token."""


class _TerminationAwareConnection(Protocol):
    """Minimal asyncpg driver surface needed for fail-stop lock ownership."""

    def add_termination_listener(self, callback: object) -> None: ...

    def remove_termination_listener(self, callback: object) -> None: ...

    def is_closed(self) -> bool: ...


class InProcessRAGIndexLock:
    """Local lock for isolated tests; production uses the PostgreSQL implementation."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self) -> AsyncIterator[str]:
        """Serialize callers sharing this lock instance."""

        async with self._lock:
            yield uuid.uuid4().hex


class PostgresAdvisoryRAGIndexLock:
    """Hold a session advisory lock on a dedicated non-pooled connection."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @asynccontextmanager
    async def hold(self) -> AsyncIterator[str]:
        """Block until this deployment has exclusive RAG index ownership.

        ``NullPool`` ensures that closing the context physically closes the PostgreSQL
        session, so a lost worker releases the session-level lock automatically.
        """

        engine = create_async_engine(self._database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                LOGGER.info("rag_index_lock_waiting")
                await connection.execute(
                    text("SELECT pg_advisory_lock(:lock_id)"),
                    {"lock_id": _RAG_INDEX_ADVISORY_LOCK_ID},
                )
                await connection.commit()
                transaction_id = await connection.scalar(text("SELECT txid_current()"))
                await connection.commit()
                if not isinstance(transaction_id, int):
                    raise RuntimeError("PostgreSQL returned an invalid RAG fencing transaction")
                generation_id = f"{transaction_id:016x}-{uuid.uuid4().hex}"
                raw_connection = await connection.get_raw_connection()
                driver_connection = cast(
                    _TerminationAwareConnection, raw_connection.driver_connection
                )
                owner_task = asyncio.current_task()
                critical_section_active = True

                def cancel_owner_on_termination(_connection: object) -> None:
                    """Fail-stop the writer as soon as its lock session disappears."""

                    if critical_section_active and owner_task is not None:
                        LOGGER.critical("rag_index_lock_connection_lost")
                        owner_task.cancel("RAG index advisory-lock connection was lost")

                driver_connection.add_termination_listener(cancel_owner_on_termination)
                LOGGER.info("rag_index_lock_acquired")
                try:
                    yield generation_id
                finally:
                    critical_section_active = False
                    driver_connection.remove_termination_listener(cancel_owner_on_termination)
                    if driver_connection.is_closed():
                        LOGGER.warning("rag_index_lock_connection_already_closed")
                    else:
                        unlocked = await connection.scalar(
                            text("SELECT pg_advisory_unlock(:lock_id)"),
                            {"lock_id": _RAG_INDEX_ADVISORY_LOCK_ID},
                        )
                        await connection.commit()
                        if unlocked is not True:
                            raise RuntimeError("PostgreSQL did not release the RAG index lock")
                        LOGGER.info("rag_index_lock_released")
        finally:
            await engine.dispose()

"""FastAPI dependency providers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.session import Database
from gerclaw_api.repositories.trace import SqlAlchemyTraceRepository
from gerclaw_api.services.trace_service import TraceService


async def get_database_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped transaction session from application state."""

    database: Database = request.app.state.database
    async with database.session() as session:
        yield session


def get_trace_service(session: AsyncSession, *, max_events_per_trace: int = 10_000) -> TraceService:
    """Build the trace service with its request-scoped repository."""

    return TraceService(
        SqlAlchemyTraceRepository(session), max_events_per_trace=max_events_per_trace
    )

"""GerClaw FastAPI application factory and runtime lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from gerclaw_api.api.routes.chat import router as chat_router
from gerclaw_api.api.routes.health import router as health_router
from gerclaw_api.api.routes.memory import router as memory_router
from gerclaw_api.api.routes.rag import router as rag_router
from gerclaw_api.api.routes.traces import router as traces_router
from gerclaw_api.config import Settings, get_settings
from gerclaw_api.database.session import Database
from gerclaw_api.encryption import configure_field_encryption
from gerclaw_api.logging import configure_logging
from gerclaw_api.middleware import (
    RequestBodyLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from gerclaw_api.modules.memory.runtime import create_memory_store
from gerclaw_api.modules.rag import (
    RAGUnavailableError,
    build_agentic_rag_middleware,
    create_rag_runtime,
)
from gerclaw_api.services.health_service import DependencyHealthService
from gerclaw_api.services.model_router import FailoverChatModel
from gerclaw_api.services.rate_limit import RateLimiter, RateLimitExceeded, RateLimitUnavailable
from gerclaw_api.services.trace_service import (
    TraceConflictError,
    TraceNotFoundError,
    TraceResourceLimitError,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an independently configurable GerClaw ASGI application."""

    resolved = settings or get_settings()
    configure_logging(resolved.log_level)
    configure_field_encryption(
        key_id=resolved.data_encryption_key_id,
        key_base64=resolved.data_encryption_key.get_secret_value(),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(resolved)
        qdrant_api_key = (
            resolved.qdrant_api_key.get_secret_value()
            if resolved.qdrant_api_key is not None
            else None
        )
        redis_client = Redis.from_url(
            resolved.redis_url,
            max_connections=resolved.redis_max_connections,
            decode_responses=True,
        )
        qdrant_client = AsyncQdrantClient(
            url=str(resolved.qdrant_url).rstrip("/"),
            api_key=qdrant_api_key or None,
        )
        rag_runtime = create_rag_runtime(resolved, qdrant_client)
        memory_store = create_memory_store(resolved, qdrant_client)
        model_configs = resolved.agent_model_configs
        app.state.database = database
        app.state.redis = redis_client
        app.state.qdrant = qdrant_client
        app.state.rag_runtime = rag_runtime
        app.state.memory_store = memory_store
        app.state.agentic_rag_middleware = build_agentic_rag_middleware(rag_runtime.module)
        app.state.agent_model = (
            FailoverChatModel(model_configs) if len(model_configs) == 3 else None
        )
        agent_model = app.state.agent_model
        app.state.rate_limiter = RateLimiter(
            redis_client,
            limit=resolved.rate_limit_requests,
            window_seconds=resolved.rate_limit_window_seconds,
        )
        app.state.health_service = DependencyHealthService(
            settings=resolved,
            database=database,
            redis_client=redis_client,
            qdrant_client=qdrant_client,
            rag_module=rag_runtime.module,
            memory_store=memory_store,
        )
        try:
            yield
        finally:
            if agent_model is not None:
                await agent_model.aclose()
            await rag_runtime.aclose()
            await qdrant_client.close()
            await redis_client.aclose()
            await database.dispose()

    app = FastAPI(
        title=resolved.app_name,
        version="0.1.0",
        docs_url="/docs" if resolved.app_env != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origin_strings,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Trace-ID"],
    )
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=resolved.max_request_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)
    app.include_router(traces_router, prefix=resolved.api_prefix)
    app.include_router(rag_router, prefix=resolved.api_prefix)
    app.include_router(chat_router, prefix=resolved.api_prefix)
    app.include_router(memory_router, prefix=resolved.api_prefix)

    @app.exception_handler(TraceNotFoundError)
    async def trace_not_found(_request: Request, error: TraceNotFoundError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "TRACE_NOT_FOUND", "message": f"trace {error} not found"}},
            status_code=404,
        )

    @app.exception_handler(TraceConflictError)
    async def trace_conflict(_request: Request, error: TraceConflictError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "TRACE_CONFLICT", "message": str(error)}},
            status_code=409,
        )

    @app.exception_handler(TraceResourceLimitError)
    async def trace_limit(_request: Request, error: TraceResourceLimitError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "TRACE_RESOURCE_LIMIT", "message": str(error)}},
            status_code=409,
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limited(_request: Request, error: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": str(error)}},
            status_code=429,
            headers={"Retry-After": str(error.retry_after_seconds)},
        )

    @app.exception_handler(RateLimitUnavailable)
    async def rate_limit_unavailable(
        _request: Request, error: RateLimitUnavailable
    ) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "RATE_LIMIT_UNAVAILABLE", "message": str(error)}},
            status_code=503,
        )

    @app.exception_handler(RAGUnavailableError)
    async def rag_unavailable(_request: Request, error: RAGUnavailableError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "RAG_UNAVAILABLE", "message": str(error)}},
            status_code=503,
        )

    return app

"""Pure-ASGI request limits, context propagation, metrics, and security headers."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import MutableMapping
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gerclaw_api.context import bind_request_context, reset_request_context
from gerclaw_api.metrics import HTTP_LATENCY, HTTP_REQUESTS

HEADER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,63}$")
TRACE_ID_PATTERN = re.compile(r"^trace_[A-Za-z0-9][A-Za-z0-9_.:-]{7,57}$")
LOGGER = logging.getLogger("gerclaw.http")


def _safe_header_id(value: str | None, prefix: str) -> str:
    if value is not None and HEADER_ID_PATTERN.fullmatch(value):
        return value
    return f"{prefix}_{uuid.uuid4().hex}"


def _safe_trace_id(value: str | None) -> str:
    if value is not None and TRACE_ID_PATTERN.fullmatch(value):
        return value
    return f"trace_{uuid.uuid4().hex}"


async def _send_json(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RequestBodyTooLarge(RuntimeError):
    """Internal control-flow exception raised before FastAPI parses JSON."""


class RequestBodyLimitMiddleware:
    """Reject declared and chunked bodies before unbounded buffering or parsing."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        declared = headers.get("content-length")
        if declared is not None:
            try:
                declared_size = int(declared)
            except ValueError:
                await _send_json(send, 400, "INVALID_CONTENT_LENGTH", "invalid Content-Length")
                return
            if declared_size < 0:
                await _send_json(send, 400, "INVALID_CONTENT_LENGTH", "invalid Content-Length")
                return
            if declared_size > self.max_body_bytes:
                await _send_json(send, 413, "REQUEST_BODY_TOO_LARGE", "request body exceeds limit")
                return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLarge:
            if response_started:  # pragma: no cover - no current route streams request reads
                raise
            await _send_json(send, 413, "REQUEST_BODY_TOO_LARGE", "request body exceeds limit")


class RequestContextMiddleware:
    """Keep correlation context alive through the final streaming response chunk."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        request_id = _safe_header_id(headers.get("x-request-id"), "req")
        trace_id = _safe_trace_id(headers.get("x-trace-id"))
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["trace_id"] = trace_id
        tokens = bind_request_context(request_id, trace_id)
        started = time.perf_counter()
        status = 500

        async def send_with_context(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
                mutable = MutableHeaders(scope=message)
                mutable["X-Request-ID"] = str(state["request_id"])
                mutable["X-Trace-ID"] = str(state["trace_id"])
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        finally:
            duration = time.perf_counter() - started
            route = scope.get("route")
            route_label = getattr(route, "path", "unmatched")
            method = str(scope.get("method", "UNKNOWN"))
            HTTP_REQUESTS.labels(method=method, route=route_label, status=str(status)).inc()
            HTTP_LATENCY.labels(method=method, route=route_label).observe(duration)
            LOGGER.info(
                "http_request",
                extra={
                    "http_method": method,
                    "http_route": route_label,
                    "http_status": status,
                    "duration_ms": round(duration * 1_000, 3),
                },
            )
            reset_request_context(tokens)


class SecurityHeadersMiddleware:
    """Apply conservative browser and cache headers to every API response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
            await send(message)

        await self.app(scope, receive, send_with_security)


def set_active_trace(scope: MutableMapping[str, Any], trace_id: str) -> None:
    """Bind a durable path/body Trace ID for response headers and downstream logs."""

    scope.setdefault("state", {})["trace_id"] = trace_id
    from gerclaw_api.context import trace_id_var

    trace_id_var.set(trace_id)

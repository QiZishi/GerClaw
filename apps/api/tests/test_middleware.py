"""Pure-ASGI body limits, streaming context, and response-header tests."""

from __future__ import annotations

import json
from typing import Any

import pytest
from starlette.types import ASGIApp, Message, Scope

from gerclaw_api.context import request_id_var, trace_id_var
from gerclaw_api.middleware import (
    RequestBodyLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)


def _scope(headers: list[tuple[bytes, bytes]] | None = None) -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/test",
        "raw_path": b"/test",
        "query_string": b"",
        "root_path": "",
        "headers": headers or [],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
        "state": {},
    }


async def _invoke(
    app: ASGIApp,
    *,
    scope: Scope,
    incoming: list[Message] | None = None,
) -> list[Message]:
    messages = list(incoming or [{"type": "http.request", "body": b"", "more_body": False}])
    sent: list[Message] = []

    async def receive() -> Message:
        return messages.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


@pytest.mark.asyncio
async def test_body_limit_rejects_declared_invalid_and_chunked_oversize() -> None:
    async def inner(scope: Scope, receive: Any, send: Any) -> None:
        await receive()
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestBodyLimitMiddleware(inner, max_body_bytes=16)
    declared = await _invoke(
        middleware,
        scope=_scope([(b"content-length", b"17")]),
    )
    invalid = await _invoke(
        middleware,
        scope=_scope([(b"content-length", b"invalid")]),
    )
    chunked = await _invoke(
        middleware,
        scope=_scope(),
        incoming=[{"type": "http.request", "body": b"x" * 17, "more_body": False}],
    )

    assert declared[0]["status"] == 413
    assert invalid[0]["status"] == 400
    assert chunked[0]["status"] == 413
    assert json.loads(chunked[1]["body"])["error"]["code"] == "REQUEST_BODY_TOO_LARGE"


@pytest.mark.asyncio
async def test_context_and_security_headers_cover_complete_stream() -> None:
    observed: list[tuple[str, str]] = []

    async def inner(scope: Scope, receive: Any, send: Any) -> None:
        del receive
        observed.append((request_id_var.get(), trace_id_var.get()))
        scope["state"]["trace_id"] = "trace_durable_0001"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"one", "more_body": True})
        observed.append((request_id_var.get(), trace_id_var.get()))
        await send({"type": "http.response.body", "body": b"two", "more_body": False})

    app = RequestContextMiddleware(SecurityHeadersMiddleware(inner))
    sent = await _invoke(
        app,
        scope=_scope(
            [
                (b"x-request-id", b"request_middleware_001"),
                (b"x-trace-id", b"trace_initial_0001"),
            ]
        ),
    )
    headers = {key.decode().lower(): value.decode() for key, value in sent[0]["headers"]}

    assert observed == [
        ("request_middleware_001", "trace_initial_0001"),
        ("request_middleware_001", "trace_initial_0001"),
    ]
    assert headers["x-trace-id"] == "trace_durable_0001"
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"
    assert request_id_var.get() == ""
    assert trace_id_var.get() == ""

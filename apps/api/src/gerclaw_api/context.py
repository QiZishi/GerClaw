"""Request-scoped context variables used by logs and traces."""

from __future__ import annotations

from contextvars import ContextVar, Token

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def bind_request_context(request_id: str, trace_id: str) -> tuple[Token[str], Token[str]]:
    """Bind request and trace identifiers, returning reset tokens."""

    return request_id_var.set(request_id), trace_id_var.set(trace_id)


def reset_request_context(tokens: tuple[Token[str], Token[str]]) -> None:
    """Reset request-scoped identifiers after a response finishes."""

    request_id_var.reset(tokens[0])
    trace_id_var.reset(tokens[1])

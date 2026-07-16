"""Run the bounded real-service SSE safety-short-circuit performance workload.

This is intentionally not an LLM, RAG, or capacity benchmark.  It sends a
deterministic red-flag message that the Agent Harness must resolve before any
model or retrieval call, while still exercising guest authentication, Redis
rate limiting and leases, PostgreSQL conversation writes, SSE completion and
Trace persistence through the deployed HTTP service.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import math
import os
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never

import httpx

MAX_CONCURRENCY = 10
DEFAULT_MESSAGE = "我突然胸痛并且呼吸困难。"
EXPECTED_CROSS_ACTOR_STATUS = 404


class WorkloadError(RuntimeError):
    """The deployed workload did not meet one of its explicit invariants."""


@dataclass(frozen=True, slots=True)
class GuestSession:
    """One isolated visitor identity and its server-owned session."""

    token: str
    session_id: str


@dataclass(frozen=True, slots=True)
class TurnResult:
    """One completed SSE turn and the durable identifiers it produced."""

    session_id: str
    trace_id: str
    status_code: int
    terminal_event: str
    latency_ms: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=MAX_CONCURRENCY)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _validated_args() -> argparse.Namespace:
    args = _parse_args()
    if not 2 <= args.concurrency <= MAX_CONCURRENCY:
        raise WorkloadError(f"concurrency must be between 2 and {MAX_CONCURRENCY}")
    if not 1 <= args.timeout_seconds <= 120:
        raise WorkloadError("timeout-seconds must be between 1 and 120")
    args.base_url = args.base_url.rstrip("/")
    if not args.base_url.startswith(("http://", "https://")):
        raise WorkloadError("base-url must be an HTTP(S) URL")
    return args


def _guest_signature(visitor_id: str, secret: str) -> str:
    payload = f"gerclaw-guest-bootstrap:v1:{visitor_id}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


async def _json_response(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = await client.request(method, path, headers=headers, json=body)
    if response.status_code not in {200, 201}:
        raise WorkloadError(f"{method} {path} returned HTTP {response.status_code}")
    parsed = response.json()
    if not isinstance(parsed, dict):
        raise WorkloadError(f"{method} {path} did not return a JSON object")
    return parsed


async def _create_guest_session(
    client: httpx.AsyncClient, *, secret: str
) -> GuestSession:
    visitor_id = uuid.uuid4().hex
    guest = await _json_response(
        client,
        "POST",
        "/api/v1/auth/guest",
        headers={
            "X-GerClaw-Visitor-ID": visitor_id,
            "X-GerClaw-Visitor-Signature": _guest_signature(visitor_id, secret),
        },
    )
    token = guest.get("access_token")
    if not isinstance(token, str) or len(token) < 32:
        raise WorkloadError("guest authentication response has no usable access token")
    session = await _json_response(
        client,
        "POST",
        "/api/v1/sessions",
        headers={"Authorization": f"Bearer {token}"},
        body={"session_id": str(uuid.uuid4())},
    )
    session_id = session.get("id")
    if not isinstance(session_id, str):
        raise WorkloadError("session response has no ID")
    return GuestSession(token=token, session_id=session_id)


async def _consume_sse_turn(
    client: httpx.AsyncClient, guest_session: GuestSession
) -> TurnResult:
    started = time.monotonic()
    event_name: str | None = None
    terminal_event: str | None = None
    terminal_data: dict[str, Any] | None = None
    async with client.stream(
        "POST",
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {guest_session.token}"},
        json={
            "session_id": guest_session.session_id,
            "message": DEFAULT_MESSAGE,
            "loaded_skills": [],
            "uploaded_files": [],
            "channel": "web",
            "workflow": "standard",
        },
    ) as response:
        if response.status_code != 200:
            raise WorkloadError(f"chat returned HTTP {response.status_code}")
        trace_id = response.headers.get("x-trace-id")
        if not isinstance(trace_id, str) or not trace_id.startswith("trace_"):
            raise WorkloadError("chat response has no valid Trace ID")
        async for line in response.aiter_lines():
            if not line:
                event_name = None
                continue
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ")
                continue
            if not line.startswith("data: "):
                continue
            try:
                parsed = json.loads(line.removeprefix("data: "))
            except json.JSONDecodeError as error:
                raise WorkloadError("SSE data was not valid JSON") from error
            if event_name in {"done", "error", "cancelled"}:
                if not isinstance(parsed, dict):
                    raise WorkloadError("terminal SSE data was not an object")
                terminal_event = event_name
                terminal_data = parsed
    latency_ms = max(0, round((time.monotonic() - started) * 1_000))
    if terminal_event != "done" or terminal_data is None:
        raise WorkloadError(f"SSE terminal event was {terminal_event or 'missing'}, not done")
    if terminal_data.get("trace_id") != trace_id:
        raise WorkloadError("SSE done Trace ID did not match response header")
    return TurnResult(
        session_id=guest_session.session_id,
        trace_id=trace_id,
        status_code=200,
        terminal_event=terminal_event,
        latency_ms=latency_ms,
    )


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        raise WorkloadError("cannot calculate percentile without latency values")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percentile) - 1)]


async def _verify_trace_and_messages(
    client: httpx.AsyncClient, guest_session: GuestSession, turn: TurnResult
) -> None:
    headers = {"Authorization": f"Bearer {guest_session.token}"}
    trace = await _json_response(client, "GET", f"/api/v1/traces/{turn.trace_id}", headers=headers)
    if trace.get("status") != "completed" or trace.get("session_id") != turn.session_id:
        raise WorkloadError("Trace was not completed for its own session")
    messages = await _json_response(
        client, "GET", f"/api/v1/sessions/{turn.session_id}/messages", headers=headers
    )
    items = messages.get("messages")
    if not isinstance(items, list):
        raise WorkloadError("session history did not return message list")
    matching_assistant = [
        item
        for item in items
        if isinstance(item, dict)
        and item.get("role") == "assistant"
        and item.get("trace_id") == turn.trace_id
    ]
    if not matching_assistant:
        raise WorkloadError("completed Trace has no persisted assistant message in its session")


async def _verify_cross_actor_isolation(
    client: httpx.AsyncClient, own: GuestSession, other: GuestSession
) -> int:
    response = await client.get(
        f"/api/v1/sessions/{other.session_id}/messages",
        headers={"Authorization": f"Bearer {own.token}"},
    )
    if response.status_code != EXPECTED_CROSS_ACTOR_STATUS:
        raise WorkloadError(
            f"cross-actor session read returned HTTP {response.status_code}, expected 404"
        )
    return response.status_code


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    secret = os.environ.get("GERCLAW_GUEST_IDENTITY_SECRET")
    if not secret or len(secret) < 32:
        raise WorkloadError(
            "GERCLAW_GUEST_IDENTITY_SECRET must be configured and at least 32 characters"
        )
    timeout = httpx.Timeout(args.timeout_seconds)
    limits = httpx.Limits(
        max_connections=MAX_CONCURRENCY * 2, max_keepalive_connections=MAX_CONCURRENCY * 2
    )
    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout, limits=limits) as client:
        readiness = await client.get("/health/ready")
        if readiness.status_code != 200:
            raise WorkloadError(f"health readiness returned HTTP {readiness.status_code}")
        guest_sessions = await asyncio.gather(
            *(_create_guest_session(client, secret=secret) for _ in range(args.concurrency))
        )
        turns = await asyncio.gather(
            *(_consume_sse_turn(client, item) for item in guest_sessions)
        )
        await asyncio.gather(
            *(
                _verify_trace_and_messages(client, item, turn)
                for item, turn in zip(guest_sessions, turns, strict=True)
            )
        )
        cross_actor_status = await _verify_cross_actor_isolation(
            client, guest_sessions[0], guest_sessions[1]
        )

    trace_ids = [turn.trace_id for turn in turns]
    if len(set(trace_ids)) != args.concurrency:
        raise WorkloadError("each concurrent turn must create a unique Trace")
    latencies = [turn.latency_ms for turn in turns]
    return {
        "schema_version": "perf-sse-safety-short-circuit-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "ok": True,
        "workload": {
            "kind": "deterministic_high_risk_safety_short_circuit",
            "external_model_or_rag": False,
            "claim_boundary": (
                "This is not an LLM/RAG throughput or thousand-concurrency benchmark."
            ),
        },
        "concurrency": args.concurrency,
        "timeout_seconds": args.timeout_seconds,
        "http_statuses": dict(Counter(turn.status_code for turn in turns)),
        "failure_rate": 0.0,
        "sse_terminals": dict(Counter(turn.terminal_event for turn in turns)),
        "latency_ms": {
            "min": min(latencies),
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "max": max(latencies),
        },
        "trace": {"unique_count": len(set(trace_ids)), "completed_count": len(turns)},
        "session": {
            "created_count": len(guest_sessions),
            "persisted_message_verified_count": len(turns),
            "cross_actor_read_status": cross_actor_status,
        },
    }


def _write_result(result: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")


def main() -> Never:
    try:
        args = _validated_args()
        result = asyncio.run(_run(args))
    except (WorkloadError, httpx.HTTPError, OSError) as error:
        failure = {
            "schema_version": "perf-sse-safety-short-circuit-v1",
            "ok": False,
            "error": type(error).__name__,
            "message": str(error),
        }
        print(json.dumps(failure, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from error
    _write_result(result, args.output)
    raise SystemExit(0)


if __name__ == "__main__":  # pragma: no cover - explicit CLI boundary
    main()

"""Exercise the deployed deterministic medication-review workflow at ≤10 concurrency.

This is a bounded integration workload, not a benchmark for clinical
correctness, external models, RAG, MinerU, or production capacity.  It creates
separate synthetic guest identities and sessions, prepares a valid medication
review intake for each, and times only the concurrent review request.  The
script intentionally emits aggregate, PHI-free evidence only.
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
EXPECTED_CROSS_ACTOR_STATUS = 404
SYNTHETIC_MEDICATION_LIST = "瑞舒伐他汀 40mg 每日一次\n环孢素"


class WorkloadError(RuntimeError):
    """A deployed-workload invariant was not met."""


@dataclass(frozen=True, slots=True)
class PreparedIntake:
    """A synthetic, owner-scoped workflow ready for the measured operation."""

    token: str
    session_id: str
    intake_id: str


@dataclass(frozen=True, slots=True)
class ReviewResult:
    """The PHI-free result metadata needed for verification and reporting."""

    intake_id: str
    session_id: str
    trace_id: str
    status_code: int
    finding_count: int
    source_count: int
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
) -> tuple[dict[str, Any], httpx.Headers]:
    response = await client.request(method, path, headers=headers, json=body)
    if response.status_code not in {200, 201}:
        raise WorkloadError(f"{method} {path} returned HTTP {response.status_code}")
    parsed = response.json()
    if not isinstance(parsed, dict):
        raise WorkloadError(f"{method} {path} did not return a JSON object")
    return parsed, response.headers


async def _prepare_intake(client: httpx.AsyncClient, *, secret: str) -> PreparedIntake:
    visitor_id = uuid.uuid4().hex
    guest, _ = await _json_response(
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
    headers = {"Authorization": f"Bearer {token}"}
    session, _ = await _json_response(
        client,
        "POST",
        "/api/v1/sessions",
        headers=headers,
        body={"session_id": str(uuid.uuid4())},
    )
    session_id = session.get("id")
    if not isinstance(session_id, str):
        raise WorkloadError("session response has no ID")
    intake, _ = await _json_response(
        client,
        "POST",
        "/api/v1/clinical-intakes",
        headers=headers,
        body={"session_id": session_id, "kind": "medication_review"},
    )
    intake_id = intake.get("intake_id")
    revision = intake.get("revision")
    if not isinstance(intake_id, str) or not isinstance(revision, int):
        raise WorkloadError("intake start response lacks ID or revision")
    updated, _ = await _json_response(
        client,
        "PATCH",
        f"/api/v1/clinical-intakes/{intake_id}",
        headers=headers,
        body={
            "expected_revision": revision,
            "answers": {
                "medication_list": SYNTHETIC_MEDICATION_LIST,
                "review_goal": "核对合成并发验证的规则闭环",
            },
        },
    )
    if updated.get("revision") != revision + 1:
        raise WorkloadError("intake update did not advance its revision")
    return PreparedIntake(token=token, session_id=session_id, intake_id=intake_id)


async def _run_review(client: httpx.AsyncClient, intake: PreparedIntake) -> ReviewResult:
    started = time.monotonic()
    response = await client.post(
        f"/api/v1/clinical-intakes/{intake.intake_id}/medication-review-draft",
        headers={"Authorization": f"Bearer {intake.token}"},
        json={"patient_age": 72},
    )
    latency_ms = max(0, round((time.monotonic() - started) * 1_000))
    if response.status_code != 200:
        raise WorkloadError(f"medication review returned HTTP {response.status_code}")
    trace_id = response.headers.get("x-trace-id")
    if not isinstance(trace_id, str) or not trace_id.startswith("trace_"):
        raise WorkloadError("medication review response has no valid Trace ID")
    body = response.json()
    if not isinstance(body, dict):
        raise WorkloadError("medication review response was not a JSON object")
    findings = body.get("findings")
    sources = body.get("sources")
    coverage = body.get("coverage")
    if (
        body.get("ruleset_version") != "medication-rules-v3"
        or not isinstance(findings, list)
        or not findings
        or not isinstance(sources, list)
        or not sources
        or not isinstance(coverage, dict)
        or set(coverage) != {"ddi", "dose", "beers"}
    ):
        raise WorkloadError("medication review did not return its source-traceable rule contract")
    return ReviewResult(
        intake_id=intake.intake_id,
        session_id=intake.session_id,
        trace_id=trace_id,
        status_code=response.status_code,
        finding_count=len(findings),
        source_count=len(sources),
        latency_ms=latency_ms,
    )


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        raise WorkloadError("cannot calculate percentile without latency values")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percentile) - 1)]


async def _verify_trace(
    client: httpx.AsyncClient, intake: PreparedIntake, result: ReviewResult
) -> None:
    trace, _ = await _json_response(
        client,
        "GET",
        f"/api/v1/traces/{result.trace_id}",
        headers={"Authorization": f"Bearer {intake.token}"},
    )
    if (
        trace.get("status") != "completed"
        or trace.get("session_id") != result.session_id
        or trace.get("execution_type") != "medication_review.generate"
    ):
        raise WorkloadError("review Trace was not completed for its own session")


async def _verify_cross_actor_isolation(
    client: httpx.AsyncClient, own: PreparedIntake, other: ReviewResult
) -> dict[str, int]:
    headers = {"Authorization": f"Bearer {own.token}"}
    trace = await client.get(f"/api/v1/traces/{other.trace_id}", headers=headers)
    intake = await client.get(f"/api/v1/clinical-intakes/{other.intake_id}", headers=headers)
    statuses = {"trace": trace.status_code, "intake": intake.status_code}
    if any(status != EXPECTED_CROSS_ACTOR_STATUS for status in statuses.values()):
        raise WorkloadError("cross-actor clinical artifact read was not denied with HTTP 404")
    return statuses


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    secret = os.environ.get("GERCLAW_GUEST_IDENTITY_SECRET")
    if not secret or len(secret) < 32:
        raise WorkloadError(
            "GERCLAW_GUEST_IDENTITY_SECRET must be configured and at least 32 characters"
        )
    timeout = httpx.Timeout(args.timeout_seconds)
    limits = httpx.Limits(
        max_connections=MAX_CONCURRENCY * 3, max_keepalive_connections=MAX_CONCURRENCY * 3
    )
    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout, limits=limits) as client:
        readiness = await client.get("/health/ready")
        if readiness.status_code != 200:
            raise WorkloadError(f"health readiness returned HTTP {readiness.status_code}")
        prepared = await asyncio.gather(
            *(_prepare_intake(client, secret=secret) for _ in range(args.concurrency))
        )
        results = await asyncio.gather(*(_run_review(client, intake) for intake in prepared))
        await asyncio.gather(
            *(
                _verify_trace(client, intake, result)
                for intake, result in zip(prepared, results, strict=True)
            )
        )
        cross_actor_statuses = await _verify_cross_actor_isolation(client, prepared[0], results[1])

    trace_ids = [result.trace_id for result in results]
    if len(set(trace_ids)) != args.concurrency:
        raise WorkloadError("each concurrent review must create a unique Trace")
    latencies = [result.latency_ms for result in results]
    return {
        "schema_version": "perf-medication-review-workflow-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "ok": True,
        "workload": {
            "kind": "deterministic_source_traceable_medication_review",
            "external_model_or_rag": False,
            "timed_operation": "medication_review_draft_after_prepared_intake",
            "claim_boundary": (
                "This is not clinical validation, LLM/RAG throughput, MinerU performance, or a "
                "thousand-concurrency benchmark."
            ),
        },
        "concurrency": args.concurrency,
        "timeout_seconds": args.timeout_seconds,
        "http_statuses": dict(Counter(result.status_code for result in results)),
        "failure_rate": 0.0,
        "latency_ms": {
            "min": min(latencies),
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "max": max(latencies),
        },
        "trace": {"unique_count": len(set(trace_ids)), "completed_count": len(results)},
        "review_contract": {
            "ruleset_version": "medication-rules-v3",
            "reviews_with_findings": sum(result.finding_count > 0 for result in results),
            "reviews_with_sources": sum(result.source_count > 0 for result in results),
        },
        "isolation": {"cross_actor_read_status": cross_actor_statuses},
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
            "schema_version": "perf-medication-review-workflow-v1",
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

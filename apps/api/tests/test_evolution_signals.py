"""Privacy, idempotency, failure-isolation, and export tests for evolution signals."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select

from gerclaw_api.database.models import (
    AgentRun,
    EvolutionSignalRecord,
    ExecutionTrace,
)
from gerclaw_api.modules.agent_harness.evolution_signals import (
    EvolutionSignal,
    EvolutionSignalError,
    EvolutionSignalProjector,
    EvolutionSignalSource,
)
from gerclaw_api.repositories.evolution_signal import (
    SqlAlchemyEvolutionSignalRepository,
)
from gerclaw_api.services import chat_service as chat_service_module
from gerclaw_api.services.evolution_signal_service import (
    DatabaseEvolutionSignalCollector,
    EvolutionSignalExporter,
)


def _source(**updates: object) -> EvolutionSignalSource:
    values: dict[str, object] = {
        "run_id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
        "route": "standard",
        "run_status": "completed",
        "capability_ids": ("gerclaw.cga",),
        "skill_ids": ("medication_review",),
        "input_tokens": 120,
        "output_tokens": 80,
        "duration_ms": 250,
        "feedback_value": 1,
        "feedback_revision": 2,
        "occurred_at": datetime(2026, 7, 30, 12, tzinfo=UTC),
    }
    values.update(updates)
    return EvolutionSignalSource.model_validate(values)


def test_projection_is_stable_keyed_and_contains_no_run_identifier() -> None:
    source = _source()
    first = EvolutionSignalProjector(b"a" * 32).project(source)
    replay = EvolutionSignalProjector(b"a" * 32).project(source)
    other_key = EvolutionSignalProjector(b"b" * 32).project(source)

    assert first == replay
    assert first.run_fingerprint != other_key.run_fingerprint
    assert str(source.run_id) not in first.model_dump_json()
    assert "medication_review" not in first.model_dump_json()
    assert first.skill_ids[0].startswith("skill_")
    assert first.risk_level == "medium"
    assert set(first.model_dump()) == {
        "schema_version",
        "run_fingerprint",
        "route",
        "run_status",
        "error_code",
        "risk_level",
        "capability_ids",
        "skill_ids",
        "input_tokens",
        "output_tokens",
        "duration_ms",
        "feedback_value",
        "feedback_revision",
        "occurred_at",
    }


@pytest.mark.parametrize(
    ("route", "risk"),
    [
        ("quick", "low"),
        ("standard", "medium"),
        ("deep", "high"),
        ("emergency", "critical"),
    ],
)
def test_route_risk_projection_is_code_owned(route: str, risk: str) -> None:
    signal = EvolutionSignalProjector(b"a" * 32).project(_source(route=route))
    assert signal.risk_level == risk


def test_projection_rejects_short_key_and_content_bearing_identifiers() -> None:
    with pytest.raises(EvolutionSignalError, match="KEY_TOO_SHORT"):
        EvolutionSignalProjector(b"short")
    with pytest.raises(ValidationError):
        _source(skill_ids=("请记住患者的手机号13800138000",))
    with pytest.raises(ValidationError):
        _source(error_code="模型说患者可能患癌")
    with pytest.raises(ValidationError, match="require exactly one"):
        _source(run_status="failed")
    with pytest.raises(ValidationError, match="require exactly one"):
        _source(error_code="CHAT_EXECUTION_FAILED")
    sensitive_source = _source(skill_ids=("patient-alice-diabetes",))
    sensitive_signal = EvolutionSignalProjector(b"a" * 32).project(sensitive_source)
    assert "alice" not in sensitive_signal.model_dump_json()
    assert "diabetes" not in sensitive_signal.model_dump_json()


@pytest.mark.asyncio
async def test_best_effort_collection_never_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = DatabaseEvolutionSignalCollector(
        object(),  # type: ignore[arg-type]
        hmac_key=b"a" * 32,
        timeout_seconds=0.05,
        max_pending=2,
        max_concurrent=1,
    )

    async def fail(_run_id: uuid.UUID) -> EvolutionSignal | None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(collector, "collect", fail)
    collector.schedule(uuid.uuid4())
    await collector.wait_pending()


@pytest.mark.asyncio
async def test_scheduler_is_bounded_and_times_out_without_blocking_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = DatabaseEvolutionSignalCollector(
        object(),  # type: ignore[arg-type]
        hmac_key=b"a" * 32,
        timeout_seconds=0.05,
        max_pending=1,
        max_concurrent=1,
    )
    blocked = asyncio.Event()

    async def wait_forever(_run_id: uuid.UUID) -> EvolutionSignal | None:
        await blocked.wait()
        return None

    monkeypatch.setattr(collector, "collect", wait_forever)
    collector.schedule(uuid.uuid4())
    collector.schedule(uuid.uuid4())
    assert len(collector._tasks) == 1
    await asyncio.wait_for(collector.wait_pending(), timeout=0.5)
    assert not collector._tasks


@pytest.mark.asyncio
async def test_scheduler_never_exceeds_injected_database_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = DatabaseEvolutionSignalCollector(
        object(),  # type: ignore[arg-type]
        hmac_key=b"a" * 32,
        timeout_seconds=1,
        max_pending=20,
        max_concurrent=2,
    )
    release = asyncio.Event()
    two_active = asyncio.Event()
    active = 0
    maximum_active = 0

    async def observe(_run_id: uuid.UUID) -> EvolutionSignal | None:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        if active == 2:
            two_active.set()
        try:
            await release.wait()
        finally:
            active -= 1
        return None

    monkeypatch.setattr(collector, "collect", observe)
    for _ in range(10):
        collector.schedule(uuid.uuid4())
    await asyncio.wait_for(two_active.wait(), timeout=0.5)
    await asyncio.sleep(0)
    assert maximum_active == 2
    release.set()
    await asyncio.wait_for(collector.wait_pending(), timeout=0.5)
    assert maximum_active == 2


def test_signal_json_encoding_has_no_content_or_identity_fields() -> None:
    signal = EvolutionSignalProjector(b"a" * 32).project(_source())
    encoded = json.dumps(
        signal.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    decoded = json.loads(encoded)

    forbidden = {
        "tenant_id",
        "actor_id",
        "run_id",
        "conversation_id",
        "trace_id",
        "user_text",
        "assistant_text",
        "retrieved_text",
        "provider_payload",
        "filename",
    }
    assert forbidden.isdisjoint(decoded)
    assert decoded["feedback_value"] == 1
    assert decoded["feedback_revision"] == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_terminal_run_and_feedback_reconcile_one_real_signal(
    integration_client: tuple[AsyncClient, object],
) -> None:
    client, raw_app = integration_client
    app = cast(Any, raw_app)
    session_id = uuid.uuid4()
    trace_id = "trace_evolution_signal_0001"
    created = await client.post(
        "/api/v1/sessions",
        json={"session_id": str(session_id)},
    )
    assert created.status_code == 201, created.text

    response = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": trace_id},
        json={
            "session_id": str(session_id),
            "message": "我现在胸痛并且呼吸困难",
            "channel": "web",
        },
    )
    assert response.status_code == 200, response.text
    assert "event: done" in response.text
    await app.state.evolution_signal_collector.wait_pending()

    async with app.state.database.session() as session:
        run = await session.scalar(select(AgentRun).where(AgentRun.trace_id == trace_id))
        assert run is not None
        record = await session.scalar(select(EvolutionSignalRecord))
        assert record is not None
        assert record.run_status == "completed"
        assert record.route == "emergency"
        assert record.risk_level == "critical"
        assert record.input_tokens == record.output_tokens == 0
        expected_fingerprint = EvolutionSignalProjector(
            app.state.settings.evolution_signal_hmac_key.get_secret_value().encode()
        ).project(_source(run_id=run.id, route="emergency"))
        assert record.run_fingerprint == expected_fingerprint.run_fingerprint
        run_id = run.id

    liked = await client.put(
        f"/api/v1/runs/{run_id}/feedback",
        json={"value": 1, "expected_revision": 0},
    )
    replay = await client.put(
        f"/api/v1/runs/{run_id}/feedback",
        json={"value": 1, "expected_revision": 1},
    )
    assert liked.status_code == replay.status_code == 200
    assert liked.json() == replay.json()
    await app.state.evolution_signal_collector.wait_pending()

    async with app.state.database.session() as session:
        record_count = await session.scalar(
            select(func.count()).select_from(EvolutionSignalRecord)
        )
        record = await session.scalar(select(EvolutionSignalRecord))
        assert record_count == 1
        assert record is not None
        assert record.feedback_value == 1
        assert record.feedback_revision == 1

        stale = EvolutionSignal.model_validate(
            {
                "schema_version": record.schema_version,
                "run_fingerprint": record.run_fingerprint,
                "route": record.route,
                "run_status": record.run_status,
                "error_code": record.error_code,
                "risk_level": record.risk_level,
                "capability_ids": tuple(record.capability_ids),
                "skill_ids": tuple(record.skill_ids),
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "duration_ms": record.duration_ms,
                "feedback_value": 0,
                "feedback_revision": 0,
                "occurred_at": record.occurred_at,
            }
        )
        repository = SqlAlchemyEvolutionSignalRepository(session)
        await repository.reconcile(stale)
        await repository.commit()

    async with app.state.database.session() as session:
        record = await session.scalar(select(EvolutionSignalRecord))
        assert record is not None
        assert record.feedback_value == 1
        assert record.feedback_revision == 1

    exported = await EvolutionSignalExporter(app.state.database).jsonl_page(limit=10)
    exported_rows = [json.loads(line) for line in exported.decode().splitlines()]
    assert len(exported_rows) == 1
    assert exported_rows[0]["run_fingerprint"] == record.run_fingerprint
    assert {
        "tenant_id",
        "actor_id",
        "run_id",
        "conversation_id",
        "trace_id",
        "user_text",
        "assistant_text",
    }.isdisjoint(exported_rows[0])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_run_is_collected_through_central_journal_transition(
    integration_client: tuple[AsyncClient, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, raw_app = integration_client
    app = cast(Any, raw_app)
    session_id = uuid.uuid4()
    trace_id = "trace_evolution_failed_0001"
    created = await client.post(
        "/api/v1/sessions",
        json={"session_id": str(session_id)},
    )
    assert created.status_code == 201, created.text

    async def fail_harness(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("injected harness failure")

    monkeypatch.setattr(
        chat_service_module.ProductionAgentHarness,  # type: ignore[attr-defined]
        "process_message",
        fail_harness,
    )
    response = await client.post(
        "/api/v1/chat",
        headers={"X-Trace-ID": trace_id},
        json={
            "session_id": str(session_id),
            "message": "你好 请简短回复",
            "channel": "web",
        },
    )
    assert response.status_code == 200
    assert "event: error" in response.text
    await app.state.evolution_signal_collector.wait_pending()

    async with app.state.database.session() as session:
        run = await session.scalar(select(AgentRun).where(AgentRun.trace_id == trace_id))
        assert run is not None
        record = await session.scalar(select(EvolutionSignalRecord))
        assert record is not None
        assert run.status == record.run_status == "failed"
        assert record.error_code == "CHAT_EXECUTION_FAILED"
        trace = await session.scalar(
            select(ExecutionTrace).where(ExecutionTrace.trace_id == trace_id)
        )
        assert trace is not None
        trace.error_code = "chat_patient_alice_diabetes"
        await session.commit()
        run_id = run.id

    await app.state.evolution_signal_collector.collect(run_id)
    async with app.state.database.session() as session:
        record = await session.scalar(select(EvolutionSignalRecord))
        assert record is not None
        assert record.error_code == "CHAT_EXECUTION_FAILED"

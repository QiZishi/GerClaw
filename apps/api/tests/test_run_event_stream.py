"""Durable RunEvent to public SSE projection."""

import uuid
from datetime import UTC, datetime

from gerclaw_api.api.routes.runs import _encode_run_event
from gerclaw_api.domain.run_schemas import RunEventRead


def _event(
    *,
    event_type: str,
    status: str,
    payload: dict[str, object] | None = None,
) -> RunEventRead:
    return RunEventRead(
        run_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
        sequence=7,
        event_type=event_type,
        status=status,
        public_summary="已恢复执行" if event_type == "run.resumed" else None,
        payload=payload or {},
        created_at=datetime(2026, 7, 29, tzinfo=UTC),
    )


def test_replay_preserves_durable_cursor_on_text_events() -> None:
    encoded = _encode_run_event(
        _event(
            event_type="text_delta",
            status="running",
            payload={"content": "您好"},
        ),
        trace_id="trace_run_stream_0001",
    )
    assert encoded.startswith("id: 7\nevent: text_delta\n")
    assert '"content":"您好"' in encoded
    assert '"sequence":7' in encoded
    assert '"run_id":"00000000-0000-4000-8000-000000000001"' in encoded


def test_replay_projects_resume_as_public_thinking_summary() -> None:
    encoded = _encode_run_event(
        _event(event_type="run.resumed", status="running"),
        trace_id="trace_run_stream_0001",
    )
    assert "event: thinking" in encoded
    assert '"content":"已恢复执行"' in encoded
    assert '"status":"running"' in encoded


def test_replay_projects_cancelled_terminal_without_private_payload() -> None:
    encoded = _encode_run_event(
        _event(event_type="run.status", status="cancelled"),
        trace_id="trace_run_stream_0001",
    )
    assert "event: cancelled" in encoded
    assert '"trace_id":"trace_run_stream_0001"' in encoded
    assert '"status":"cancelled"' in encoded

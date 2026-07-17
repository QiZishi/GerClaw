"""Contract tests for the real Harness-to-browser SSE validation boundary."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.modules.agent_harness import StreamEvent
from gerclaw_api.modules.validation import (
    StreamContractValidationError,
    validate_harness_stream_event,
    validate_public_chat_stream_event,
)


def _safety() -> dict[str, object]:
    return {
        "reviewed": True,
        "disclaimer_applied": True,
        "deterministic_diagnosis_blocked": False,
        "high_risk_escalation_checked": True,
        "notices": ["medical_disclaimer_applied"],
    }


def test_harness_terminal_contract_requires_only_harness_owned_fields() -> None:
    event = StreamEvent(
        event_type="done",
        data={"full_text": "请携带检查资料就医。", "references": [], "safety": _safety()},
        timestamp=datetime.now(UTC),
    )

    validated = validate_harness_stream_event(event)

    assert validated.data["full_text"] == "请携带检查资料就医。"
    assert "trace_id" not in validated.data


def test_public_terminal_contract_requires_trace_and_session_provenance() -> None:
    event = StreamEvent(
        event_type="done",
        data={
            "full_text": "请携带检查资料就医。",
            "references": [],
            "safety": _safety(),
            "trace_id": "trace_validation_0001",
            "session_id": str(uuid.uuid4()),
            "replayed": False,
        },
        timestamp=datetime.now(UTC),
    )

    validated = validate_public_chat_stream_event(event)

    assert validated.data["trace_id"] == "trace_validation_0001"
    assert validated.data["replayed"] is False


def test_public_boundary_rejects_harness_only_done_and_unknown_event_fields() -> None:
    harness_done = StreamEvent(
        event_type="done",
        data={"full_text": "请携带检查资料就医。", "references": [], "safety": _safety()},
        timestamp=datetime.now(UTC),
    )
    malformed_delta = StreamEvent(
        event_type="text_delta",
        data={"content": "您好", "provider_secret": "must-not-cross-boundary"},
        timestamp=datetime.now(UTC),
    )

    with pytest.raises(StreamContractValidationError, match="invalid public-chat-sse-v1 done"):
        validate_public_chat_stream_event(harness_done)
    with pytest.raises(StreamContractValidationError, match="invalid public-chat-sse-v1 text_delta"):
        validate_harness_stream_event(malformed_delta)

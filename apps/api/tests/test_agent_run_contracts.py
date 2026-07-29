"""Contract tests for durable Agent run, event, artifact, and feedback APIs."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from gerclaw_api.domain.run_schemas import (
    AgentRunCreate,
    AgentRunRead,
    AgentRunStatus,
    ArtifactWrite,
    FeedbackReconcileRequest,
    RunEventRead,
    RunEventWrite,
)
from gerclaw_api.modules.agent_harness.routing import RouteKind


def _run(**updates: object) -> AgentRunRead:
    values = {
        "id": uuid4(),
        "conversation_id": uuid4(),
        "input_message_id": uuid4(),
        "trace_id": "trace_abcdefgh",
        "route": RouteKind.STANDARD,
        "status": AgentRunStatus.RUNNING,
        "revision": 1,
        "started_at": datetime.now(UTC),
    }
    values.update(updates)
    return AgentRunRead.model_validate(values)


def test_terminal_run_requires_exact_terminal_timestamp_semantics() -> None:
    with pytest.raises(ValidationError, match="completed_at"):
        _run(status=AgentRunStatus.COMPLETED)
    with pytest.raises(ValidationError, match="non-terminal"):
        _run(completed_at=datetime.now(UTC))

    completed = _run(
        status=AgentRunStatus.COMPLETED_WITH_WARNINGS,
        warnings=("artifact_save_failed",),
        completed_at=datetime.now(UTC),
    )
    assert completed.status is AgentRunStatus.COMPLETED_WITH_WARNINGS


def test_run_event_payload_and_public_summary_are_bounded() -> None:
    with pytest.raises(ValidationError):
        RunEventRead(
            run_id=uuid4(),
            sequence=1,
            event_type="text_delta",
            status="running",
            public_summary="a" * 5_001,
            created_at=datetime.now(UTC),
        )
    with pytest.raises(ValidationError):
        RunEventWrite(
            event_type="text_delta",
            status="running",
            payload={f"k{index}": index for index in range(51)},
        )


def test_run_create_rejects_unbounded_snapshot_and_invalid_fence() -> None:
    values = {
        "conversation_id": uuid4(),
        "input_message_id": uuid4(),
        "trace_id": "trace_abcdefgh",
        "route": RouteKind.STANDARD,
        "context_snapshot": {f"k{index}": index for index in range(101)},
        "fencing_token": 1,
    }
    with pytest.raises(ValidationError):
        AgentRunCreate.model_validate(values)
    values["context_snapshot"] = {}
    values["fencing_token"] = 0
    with pytest.raises(ValidationError):
        AgentRunCreate.model_validate(values)
    with pytest.raises(ValidationError):
        RunEventRead(
            run_id=uuid4(),
            sequence=1,
            event_type="text_delta",
            status="running",
            payload={f"k{index}": index for index in range(51)},
            created_at=datetime.now(UTC),
        )


def test_artifact_and_feedback_requests_reject_unbounded_or_stale_shapes() -> None:
    with pytest.raises(ValidationError):
        ArtifactWrite(title="a" * 301, markdown="")
    with pytest.raises(ValidationError):
        FeedbackReconcileRequest(value=1, expected_revision=-1)
    with pytest.raises(ValidationError):
        FeedbackReconcileRequest(value=2, expected_revision=0)

"""Fencing, terminal uniqueness, cancellation, and recovery transition tests."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from gerclaw_api.domain.run_schemas import AgentRunStatus
from gerclaw_api.modules.agent_harness.run_lifecycle import (
    AgentRunStateMachine,
    RunFenceConflictError,
    RunLifecycleState,
    RunRevisionConflictError,
    RunTerminalConflictError,
    RunTransitionError,
)


def _state(status: AgentRunStatus = AgentRunStatus.RUNNING) -> RunLifecycleState:
    return RunLifecycleState(
        run_id=uuid4(),
        status=status,
        revision=3,
        fencing_token=17,
        interrupted_at=(
            datetime.now(UTC)
            if status is AgentRunStatus.INTERRUPTED
            else None
        ),
        completed_at=(
            datetime.now(UTC)
            if status
            in {
                AgentRunStatus.COMPLETED,
                AgentRunStatus.COMPLETED_WITH_WARNINGS,
                AgentRunStatus.FAILED,
                AgentRunStatus.CANCELLED,
            }
            else None
        ),
    )


def test_terminal_transition_is_unique_and_cancel_is_idempotent() -> None:
    machine = AgentRunStateMachine()
    cancelled = machine.transition(
        _state(),
        AgentRunStatus.CANCELLED,
        expected_revision=3,
        fencing_token=17,
    )

    assert cancelled.revision == 4
    assert cancelled.completed_at is not None
    assert (
        machine.transition(
            cancelled,
            AgentRunStatus.CANCELLED,
            expected_revision=4,
            fencing_token=17,
        )
        is cancelled
    )
    with pytest.raises(RunTerminalConflictError):
        machine.transition(
            cancelled,
            AgentRunStatus.COMPLETED,
            expected_revision=4,
            fencing_token=17,
        )


def test_stale_revision_and_worker_fence_fail_closed() -> None:
    machine = AgentRunStateMachine()
    with pytest.raises(RunRevisionConflictError):
        machine.transition(
            _state(),
            AgentRunStatus.COMPLETED,
            expected_revision=2,
            fencing_token=17,
        )
    with pytest.raises(RunFenceConflictError):
        machine.transition(
            _state(),
            AgentRunStatus.COMPLETED,
            expected_revision=3,
            fencing_token=16,
        )


def test_interrupted_run_can_resume_but_completed_run_cannot() -> None:
    machine = AgentRunStateMachine()
    resumed = machine.transition(
        _state(AgentRunStatus.INTERRUPTED),
        AgentRunStatus.RUNNING,
        expected_revision=3,
        fencing_token=17,
    )
    assert resumed.status is AgentRunStatus.RUNNING
    assert resumed.completed_at is None
    assert resumed.interrupted_at is not None

    with pytest.raises(RunTerminalConflictError):
        machine.transition(
            _state(AgentRunStatus.COMPLETED),
            AgentRunStatus.RUNNING,
            expected_revision=3,
            fencing_token=17,
        )


def test_completed_with_warnings_requires_bounded_warning_codes() -> None:
    machine = AgentRunStateMachine()
    with pytest.raises(RunTransitionError):
        machine.transition(
            _state(),
            AgentRunStatus.COMPLETED_WITH_WARNINGS,
            expected_revision=3,
            fencing_token=17,
        )
    completed = machine.transition(
        _state(),
        AgentRunStatus.COMPLETED_WITH_WARNINGS,
        expected_revision=3,
        fencing_token=17,
        warnings=("artifact_save_failed",),
    )
    assert completed.warnings == ("artifact_save_failed",)

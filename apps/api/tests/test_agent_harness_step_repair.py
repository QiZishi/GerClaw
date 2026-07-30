"""Private step-repair classification and bounded replay tests."""

# ruff: noqa: RUF001

from __future__ import annotations

import pytest

from gerclaw_api.modules.agent_harness.run_lifecycle.agent_stream import AgentStreamResult
from gerclaw_api.modules.agent_harness.run_lifecycle.output_repair import (
    run_with_output_protocol_repair,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.step_repair import (
    StepRepairDecision,
)


class _Budget:
    def __init__(self) -> None:
        self.retries = 0

    def add_retry(self) -> None:
        self.retries += 1


def _result(text: str) -> AgentStreamResult:
    return AgentStreamResult(
        text=text,
        deterministic_diagnosis_blocked=False,
        input_tokens=10,
        output_tokens=5,
    )


@pytest.mark.asyncio
async def test_explicit_repair_replays_privately_and_publishes_only_replacement() -> None:
    attempts = 0
    published: list[str] = []
    rebuilt: list[str] = []
    observed: list[str] = []
    budget = _Budget()
    decision = StepRepairDecision(
        error_code="provider_partial_stream",
        field_paths=("answer.text",),
        contract_version="chat-answer-v1",
        checkpoint_id="chat.answer.pre_model.v1",
        instruction="重新生成完整答案，不提及失败过程。",
    )

    async def run_attempt(emit: object) -> AgentStreamResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("private partial stream")
        await emit("text_delta", {"content": "最终有效答案"})  # type: ignore[operator]
        return _result("最终有效答案")

    async def publish(_kind: str, data: dict[str, object]) -> None:
        published.append(str(data["content"]))

    async def observe(
        error_code: str,
        _field_paths: tuple[str, ...],
        _contract_version: str,
        _repair_action: str,
        _checkpoint_id: str,
    ) -> None:
        observed.append(error_code)

    result, repair_count = await run_with_output_protocol_repair(
        run_attempt=run_attempt,
        rebuild_agent=rebuilt.append,
        publish=publish,  # type: ignore[arg-type]
        budget=budget,  # type: ignore[arg-type]
        observer=observe,
        classify_failure=lambda error: decision if isinstance(error, ConnectionError) else None,
    )

    assert result.text == "最终有效答案"
    assert published == ["最终有效答案"]
    assert rebuilt == [decision.instruction]
    assert observed == ["provider_partial_stream"]
    assert repair_count == budget.retries == 1


@pytest.mark.asyncio
async def test_repeated_failure_signature_is_not_retried_in_a_loop() -> None:
    attempts = 0
    budget = _Budget()
    decision = StepRepairDecision(
        error_code="answer_schema_contract",
        field_paths=("answer",),
        contract_version="chat-answer-v1",
        checkpoint_id="chat.answer.pre_model.v1",
        instruction="按 schema 重做。",
    )

    async def run_attempt(_emit: object) -> AgentStreamResult:
        nonlocal attempts
        attempts += 1
        raise ValueError("same contract failure")

    async def publish(_kind: str, _data: dict[str, object]) -> None:
        raise AssertionError("failed attempts must stay private")

    with pytest.raises(ValueError, match="same contract failure"):
        await run_with_output_protocol_repair(
            run_attempt=run_attempt,
            rebuild_agent=lambda _instruction: None,
            publish=publish,  # type: ignore[arg-type]
            budget=budget,  # type: ignore[arg-type]
            observer=None,
            classify_failure=lambda _error: decision,
        )

    assert attempts == 2
    assert budget.retries == 1


@pytest.mark.asyncio
async def test_unclassified_authorization_failure_is_never_retried() -> None:
    attempts = 0
    budget = _Budget()

    async def run_attempt(_emit: object) -> AgentStreamResult:
        nonlocal attempts
        attempts += 1
        raise PermissionError("actor scope rejected")

    async def publish(_kind: str, _data: dict[str, object]) -> None:
        raise AssertionError("failed attempts must stay private")

    with pytest.raises(PermissionError, match="actor scope rejected"):
        await run_with_output_protocol_repair(
            run_attempt=run_attempt,
            rebuild_agent=lambda _instruction: None,
            publish=publish,  # type: ignore[arg-type]
            budget=budget,  # type: ignore[arg-type]
            observer=None,
            classify_failure=lambda _error: None,
        )

    assert attempts == 1
    assert budget.retries == 0

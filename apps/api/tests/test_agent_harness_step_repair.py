"""Private step-repair classification and bounded replay tests."""

# ruff: noqa: RUF001

from __future__ import annotations

import pytest
from agentscope.message import AssistantMsg

from gerclaw_api.modules.agent_harness.orchestration_support import (
    classify_answer_step_failure,
)
from gerclaw_api.modules.agent_harness.run_lifecycle import UnboundClinicalClaimsError
from gerclaw_api.modules.agent_harness.run_lifecycle.agent_stream import AgentStreamResult
from gerclaw_api.modules.agent_harness.run_lifecycle.output_repair import (
    RepairableAgentSession,
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


def test_rebuilt_agent_reinstalls_request_boundaries() -> None:
    configured: list[object] = []

    class _Agent:
        def __init__(self, context: object) -> None:
            self.state = type("_State", (), {"context": context})()

    session = RepairableAgentSession(
        builder=lambda context: _Agent(context),  # type: ignore[arg-type,return-value]
        base_context=[AssistantMsg(name="base", content="基础上下文")],
        configure_agent=configured.append,  # type: ignore[arg-type]
    )

    session.rebuild("按当前输出合同重新完成本步骤")

    assert len(configured) == 2
    assert configured[-1] is session.agent
    assert session.agent.state.context[-1].name == "output_contract_repair"


def test_claim_repair_preserves_the_users_presentation_contract() -> None:
    decision = classify_answer_step_failure(UnboundClinicalClaimsError(("claim-1",)))

    assert decision is not None
    assert "answer_presentation_contract" in decision.instruction
    assert "条目数量、编号格式、受众、长度和就医时机" in decision.instruction
    assert "不能因补引用而丢项" in decision.instruction


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
async def test_terminal_contract_validation_replays_before_any_text_is_published() -> None:
    attempts = 0
    published: list[str] = []
    rebuilt: list[str] = []
    budget = _Budget()
    decision = StepRepairDecision(
        error_code="answer_schema_contract",
        field_paths=("answer",),
        contract_version="chat-answer-v1",
        checkpoint_id="chat.answer.pre_model.v1",
        instruction="补齐真实证据后重新回答。",
    )

    async def run_attempt(emit: object) -> AgentStreamResult:
        nonlocal attempts
        attempts += 1
        text = "没有证据的草稿" if attempts == 1 else "带有证据的最终回答"
        await emit("text_delta", {"content": text})  # type: ignore[operator]
        return _result(text)

    def validate_result(result: AgentStreamResult) -> None:
        if "证据的最终" not in result.text:
            raise ValueError("terminal response contract rejected")

    async def publish(_kind: str, data: dict[str, object]) -> None:
        published.append(str(data["content"]))

    result, repair_count = await run_with_output_protocol_repair(
        run_attempt=run_attempt,
        rebuild_agent=rebuilt.append,
        publish=publish,  # type: ignore[arg-type]
        budget=budget,  # type: ignore[arg-type]
        observer=None,
        classify_failure=lambda error: decision if isinstance(error, ValueError) else None,
        validate_result=validate_result,
    )

    assert result.text == "带有证据的最终回答"
    assert published == ["带有证据的最终回答"]
    assert rebuilt == [decision.instruction]
    assert repair_count == budget.retries == 1


@pytest.mark.asyncio
async def test_terminal_validator_can_replace_text_before_publication() -> None:
    published: list[str] = []
    budget = _Budget()

    async def run_attempt(emit: object) -> AgentStreamResult:
        await emit("text_delta", {"content": "采用上传资料 [C3]。"})  # type: ignore[operator]
        return _result("采用上传资料 [C3]。")

    async def publish(_kind: str, data: dict[str, object]) -> None:
        published.append(str(data["content"]))

    result, repair_count = await run_with_output_protocol_repair(
        run_attempt=run_attempt,
        rebuild_agent=lambda _instruction: None,
        publish=publish,  # type: ignore[arg-type]
        budget=budget,  # type: ignore[arg-type]
        observer=None,
        validate_result=lambda result: AgentStreamResult(
            text=result.text.replace("[C3]", "[C1]"),
            deterministic_diagnosis_blocked=result.deterministic_diagnosis_blocked,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        ),
    )

    assert repair_count == 0
    assert result.text == "采用上传资料 [C1]。"
    assert published == ["采用上传资料 [C1]。"]


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
async def test_repeated_repairable_failure_can_publish_localized_recovery() -> None:
    attempts = 0
    published: list[str] = []
    budget = _Budget()
    decision = StepRepairDecision(
        error_code="answer_claim_evidence",
        field_paths=("answer.clinical_claims",),
        contract_version="claim-evidence-v1",
        checkpoint_id="chat.answer.pre_model.v1",
        instruction="只重写缺证据的句子。",
    )

    async def run_attempt(emit: object) -> AgentStreamResult:
        nonlocal attempts
        attempts += 1
        text = "已有依据 [C1]。无依据的停药建议。"
        await emit("text_delta", {"content": text})  # type: ignore[operator]
        return _result(text)

    def validate_result(result: AgentStreamResult) -> None:
        if "无依据" in result.text:
            raise ValueError("claim evidence rejected")

    async def publish(_kind: str, data: dict[str, object]) -> None:
        published.append(str(data["content"]))

    result, repair_count = await run_with_output_protocol_repair(
        run_attempt=run_attempt,
        rebuild_agent=lambda _instruction: None,
        publish=publish,  # type: ignore[arg-type]
        budget=budget,  # type: ignore[arg-type]
        observer=None,
        classify_failure=lambda error: decision if isinstance(error, ValueError) else None,
        validate_result=validate_result,
        recover_repeated_failure=lambda _result_value, _error: _result("已有依据 [C1]。"),
    )

    assert attempts == 2
    assert repair_count == budget.retries == 1
    assert result.text == "已有依据 [C1]。"
    assert published == ["已有依据 [C1]。"]


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

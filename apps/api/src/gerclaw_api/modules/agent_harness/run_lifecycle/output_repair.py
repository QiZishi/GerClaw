"""Bounded private output repair before an answer attempt is promoted."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, Protocol

from agentscope.agent import Agent
from agentscope.message import Msg, SystemMsg

from gerclaw_api.modules.agent_harness.run_lifecycle.agent_stream import (
    AgentStreamResult,
    StreamBudget,
    project_agent_stream,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.errors import (
    AgentOutputProtocolError,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.public_answer import (
    project_public_answer,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.step_repair import (
    StepRepairDecision,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.streaming import (
    validate_public_answer_text,
)
from gerclaw_api.security import JsonValue

BufferedEvent = tuple[str, dict[str, JsonValue]]
BufferedEmitter = Callable[[str, dict[str, JsonValue]], Awaitable[None]]
AttemptRunner = Callable[[BufferedEmitter], Awaitable[AgentStreamResult]]
AttemptValidator = Callable[[AgentStreamResult], AgentStreamResult | None]
AttemptRecovery = Callable[[AgentStreamResult, Exception], AgentStreamResult | None]
AttemptRepairObserver = Callable[
    [str, tuple[str, ...], str, str, str],
    Awaitable[None],
]
StepFailureClassifier = Callable[[Exception], StepRepairDecision | None]
AgentConfigurer = Callable[[Agent], None]

OUTPUT_PROTOCOL_REPAIR_INSTRUCTION = (
    "上一尝试把内部工具调用格式写进了回答。重新完成用户要求:"
    "不要复述、解释或输出 invoke、parameter、tool_call、function_call、"
    "final-clinical-state 等协议标签;"
    "如需工具必须使用已提供的正式工具接口, 否则直接用自然语言回答。"
)
OUTPUT_PROTOCOL_REPAIR = StepRepairDecision(
    error_code="answer_protocol_markup",
    field_paths=("answer.text",),
    contract_version="chat-answer-v1",
    checkpoint_id="chat.answer.pre_model.v1",
    instruction=OUTPUT_PROTOCOL_REPAIR_INSTRUCTION,
)


class RetryBudget(StreamBudget, Protocol):
    """Budget operation consumed by one private repair attempt."""

    def add_retry(self) -> None: ...


class RepairableAgentSession:
    """Rebuild one request-scoped Agent from the pre-model checkpoint."""

    def __init__(
        self,
        *,
        builder: Callable[[list[Msg]], Agent],
        base_context: list[Msg],
        configure_agent: AgentConfigurer | None = None,
    ) -> None:
        self._builder = builder
        self._base_context = base_context
        self._configure_agent = configure_agent
        self.agent = self._build_agent(list(base_context))

    @classmethod
    def from_factory(
        cls,
        *,
        factory: Any,
        base_context: list[Msg],
        configure_agent: AgentConfigurer | None = None,
        **build_kwargs: Any,
    ) -> RepairableAgentSession:
        return cls(
            builder=lambda current: factory.build(
                state_context=current,
                **build_kwargs,
            ),
            base_context=base_context,
            configure_agent=configure_agent,
        )

    def _build_agent(self, context: list[Msg]) -> Agent:
        agent = self._builder(context)
        if self._configure_agent is not None:
            self._configure_agent(agent)
        return agent

    def rebuild(self, instruction: str = OUTPUT_PROTOCOL_REPAIR_INSTRUCTION) -> None:
        runtime_directives = [
            message
            for message in self.agent.state.context
            if message.name == "runtime_user_directive"
        ]
        self.agent = self._build_agent(
            [
                *self._base_context,
                *runtime_directives,
                SystemMsg(
                    name="output_contract_repair",
                    content=instruction,
                ),
            ]
        )


def _buffered_emitter(events: list[BufferedEvent]) -> BufferedEmitter:
    async def emit(event_type: str, data: dict[str, JsonValue]) -> None:
        events.append((event_type, data))

    return emit


def _project_answer_events(
    events: list[BufferedEvent],
    *,
    original_text: str,
    public_text: str,
) -> list[BufferedEvent]:
    if public_text == original_text:
        return events
    non_text_events = [event for event in events if event[0] != "text_delta"]
    if public_text:
        non_text_events.append(("text_delta", {"content": public_text}))
    return non_text_events


async def run_with_output_protocol_repair(
    *,
    run_attempt: AttemptRunner,
    rebuild_agent: Callable[[str], None],
    publish: BufferedEmitter,
    budget: RetryBudget,
    observer: AttemptRepairObserver | None,
    classify_failure: StepFailureClassifier | None = None,
    validate_result: AttemptValidator | None = None,
    recover_repeated_failure: AttemptRecovery | None = None,
) -> tuple[AgentStreamResult, int]:
    """Retry explicitly classified private failures without exposing bad output."""

    repair_count = 0
    seen_failures: set[tuple[str, tuple[str, ...], str, str]] = set()
    while True:
        events: list[BufferedEvent] = []
        result: AgentStreamResult | None = None
        original_text = ""
        public_text = ""
        try:
            result = await run_attempt(_buffered_emitter(events))
            original_text = result.text
            public_text = project_public_answer(original_text)
            validate_public_answer_text(public_text)
            result = replace(result, text=public_text)
            if validate_result is not None:
                validated_result = validate_result(result)
                if validated_result is not None:
                    result = validated_result
                    public_text = result.text
                    validate_public_answer_text(public_text)
        except Exception as error:
            decision = (
                OUTPUT_PROTOCOL_REPAIR
                if isinstance(error, AgentOutputProtocolError)
                else classify_failure(error)
                if classify_failure is not None
                else None
            )
            repeated_failure = decision is not None and (
                decision.signature in seen_failures or repair_count >= 1
            )
            if decision is None or repeated_failure:
                recovered = (
                    recover_repeated_failure(result, error)
                    if repeated_failure
                    and result is not None
                    and recover_repeated_failure is not None
                    else None
                )
                if recovered is None:
                    raise
                public_text = project_public_answer(recovered.text)
                validate_public_answer_text(public_text)
                result = replace(recovered, text=public_text)
                if validate_result is not None:
                    try:
                        validated_result = validate_result(result)
                    except Exception:
                        validated_result = None
                    if validated_result is not None:
                        result = validated_result
                        public_text = result.text
                        validate_public_answer_text(public_text)
            else:
                seen_failures.add(decision.signature)
                budget.add_retry()
                if observer is not None:
                    await observer(
                        decision.error_code,
                        decision.field_paths,
                        decision.contract_version,
                        decision.repair_action,
                        decision.checkpoint_id,
                    )
                rebuild_agent(decision.instruction)
                repair_count += 1
                continue
        if result is None:
            raise RuntimeError("OUTPUT_REPAIR_NO_RESULT")
        projected_events = _project_answer_events(
            events,
            original_text=original_text,
            public_text=public_text,
        )
        for event_type, data in projected_events:
            await publish(event_type, data)
        return result, repair_count


async def project_with_output_protocol_repair(
    *,
    session: RepairableAgentSession,
    publish: BufferedEmitter,
    budget: RetryBudget,
    observer: AttemptRepairObserver | None,
    classify_failure: StepFailureClassifier | None = None,
    validate_result: AttemptValidator | None = None,
    recover_repeated_failure: AttemptRecovery | None = None,
    **project_kwargs: Any,
) -> tuple[AgentStreamResult, int]:
    """Bind the generic repair loop to the AgentScope stream projector."""

    async def run_attempt(emit: BufferedEmitter) -> AgentStreamResult:
        return await project_agent_stream(
            agent=session.agent,
            emit=emit,
            budget=budget,
            **project_kwargs,
        )

    return await run_with_output_protocol_repair(
        run_attempt=run_attempt,
        rebuild_agent=session.rebuild,
        publish=publish,
        budget=budget,
        observer=observer,
        classify_failure=classify_failure,
        validate_result=validate_result,
        recover_repeated_failure=recover_repeated_failure,
    )

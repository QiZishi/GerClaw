"""Focused orchestration support kept outside the bounded composition entry."""

# ruff: noqa: RUF001

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from agentscope.message import ToolCallBlock
from pydantic import BaseModel

from gerclaw_api.modules.agent_harness.config import ResolvedHarnessConfig
from gerclaw_api.modules.agent_harness.planning import emit_deterministic_clarification
from gerclaw_api.modules.agent_harness.plugin_runtime import (
    ApprovalCallback,
    ApprovalCoordinator,
)
from gerclaw_api.modules.agent_harness.protocols import StreamEvent
from gerclaw_api.modules.agent_harness.run_lifecycle import bounded_events
from gerclaw_api.modules.agent_harness.run_lifecycle.directive_runtime import (
    RuntimeDirectiveCoordinator,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.step_repair import (
    StepRepairDecision,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.terminal_contract import (
    UnboundClinicalClaimsError,
)
from gerclaw_api.modules.agent_harness.safety import HIGH_RISK_NOTICE
from gerclaw_api.modules.contracts import AgentResponse, ExecutionContext
from gerclaw_api.modules.runtime.budget import (
    RuntimeBudgetExceededError,
    RuntimeBudgetTracker,
)
from gerclaw_api.modules.runtime.models import (
    ExecutionBudget,
    RuntimePrincipal,
    ToolCapability,
)
from gerclaw_api.modules.runtime.registry import ToolInputInvalidError
from gerclaw_api.modules.validation import validate_harness_stream_event
from gerclaw_api.modules.validation.contracts import ModelOutputContractValidationError
from gerclaw_api.security import JsonValue
from gerclaw_api.services.model_router import PartialModelStreamError

_PARTIAL_PROVIDER_REPAIR = StepRepairDecision(
    error_code="provider_partial_stream",
    field_paths=("answer.text",),
    contract_version="chat-answer-v1",
    checkpoint_id="chat.answer.pre_model.v1",
    instruction=(
        "上一服务在回答完成前中断。请从用户要求重新生成完整答案，"
        "不要提及中断、重试、服务或已丢弃的内容。"
    ),
)
_TOOL_INPUT_REPAIR = StepRepairDecision(
    error_code="tool_input_contract",
    field_paths=("tool.arguments",),
    contract_version="governed-tool-input-v1",
    checkpoint_id="chat.answer.pre_model.v1",
    instruction=(
        "上一尝试的工具参数未通过已声明的 schema，工具尚未执行。"
        "请按工具的正式参数 schema 重新调用；如无需工具，直接用已有信息回答。"
    ),
)
_ANSWER_SCHEMA_REPAIR = StepRepairDecision(
    error_code="answer_schema_contract",
    field_paths=("answer",),
    contract_version="chat-answer-v1",
    checkpoint_id="chat.answer.pre_model.v1",
    instruction=(
        "上一尝试的回答未通过已声明的数据合同。请从本步骤重新生成完整结果，"
        "保留已核验事实，不要解释校验或重试过程。医疗事实必须在对应句使用本轮真实"
        " [E1]/[W1] 证据标记；若尚无证据，先调用可用检索工具，不能编造来源。"
    ),
)
_UNBOUND_CLAIM_REPAIR = StepRepairDecision(
    error_code="answer_claim_evidence",
    field_paths=("answer.clinical_claims",),
    contract_version="claim-evidence-v1",
    checkpoint_id="chat.answer.pre_model.v1",
    instruction=(
        "上一尝试中有医学事实或建议没有在对应句末标注本轮真实 [E1]/[W1] 证据。"
        "只修复这些缺证据的句子并重新完成答案；保留已经核验的内容。"
        "已有 answer_presentation_contract 仍是必须完成的用户要求："
        "条目数量、编号格式、受众、长度和就医时机都必须原样遵守，不能因补引用而丢项、"
        "改成普通段落或扩写用户没有要求的疾病推测。"
        "可调用正式检索工具补充证据，无法核验的具体医学结论不要输出。"
        "必须继续完成用户的任务：记录、整理、复述用户已提供信息等不需要医学证据的操作应直接保留。"
        "禁止把整个答案改写成‘资料不足’、‘无法回答’或要求用户允许检索。"
        "不要提及校验、修复或被删除的草稿。"
    ),
)


def _contains_failure(error: BaseException, error_type: type[BaseException]) -> bool:
    if isinstance(error, error_type):
        return True
    return isinstance(error, BaseExceptionGroup) and any(
        _contains_failure(item, error_type) for item in error.exceptions
    )


def classify_answer_step_failure(error: Exception) -> StepRepairDecision | None:
    """Classify only defects safe to replay from the pre-model checkpoint."""

    if _contains_failure(error, PartialModelStreamError):
        return _PARTIAL_PROVIDER_REPAIR
    if _contains_failure(error, ToolInputInvalidError):
        return _TOOL_INPUT_REPAIR
    if _contains_failure(error, UnboundClinicalClaimsError):
        return _UNBOUND_CLAIM_REPAIR
    if _contains_failure(error, ModelOutputContractValidationError):
        return _ANSWER_SCHEMA_REPAIR
    return None


class OrchestrationSupportMixin:
    """Compose owner APIs without taking ownership of their domain mechanisms."""

    _execution_budget: ExecutionBudget
    _approval_callback: ApprovalCallback | None
    _runtime_principal: RuntimePrincipal
    _execution: ExecutionContext
    _config: ResolvedHarnessConfig
    _runtime_directives: RuntimeDirectiveCoordinator

    @staticmethod
    async def _emit(
        callback: Any,
        event_type: str,
        data: dict[str, JsonValue],
    ) -> None:
        event = validate_harness_stream_event(
            StreamEvent.model_validate(
                {
                    "event_type": event_type,
                    "data": data,
                    "timestamp": datetime.now(UTC),
                }
            )
        )
        result = callback(event)
        if inspect.isawaitable(result):
            await result

    def _bounded_agent_events(
        self,
        events: AsyncIterator[Any],
    ) -> AsyncIterator[Any]:
        return bounded_events(
            events,
            wall_clock_seconds=self._execution_budget.wall_clock_seconds,
            timeout_error_factory=lambda: RuntimeBudgetExceededError("RUNTIME_WALL_CLOCK_EXCEEDED"),
        )

    async def _persist_approval_requests(
        self,
        tool_calls: list[ToolCallBlock],
        *,
        capabilities: dict[str, ToolCapability],
        input_models: dict[str, type[BaseModel]],
        stream_callback: Any,
    ) -> tuple[str, ...]:
        coordinator = ApprovalCoordinator(
            callback=self._approval_callback,
            principal=self._runtime_principal,
            execution=self._execution,
            ttl_seconds=self._config.approval_ttl_seconds,
        )
        return await coordinator.persist(
            tool_calls,
            capabilities=capabilities,
            input_models=input_models,
            emit=lambda event_type, data: self._emit(stream_callback, event_type, data),
        )

    async def _emit_runtime_directive_emergency(
        self,
        risk_codes: tuple[str, ...],
        *,
        budget: RuntimeBudgetTracker,
        stream_callback: Any,
    ) -> AgentResponse:
        return await emit_deterministic_clarification(
            body=HIGH_RISK_NOTICE,
            high_risk_codes=list(risk_codes),
            emit=lambda kind, data: self._emit(stream_callback, kind, data),
            budget=budget,
            structured={
                "emergency_short_circuit": True,
                "route": "emergency",
                "route_reason": "runtime_directive_red_flag",
                "plan_node_ids": ["safety.emergency"],
            },
            emergency_short_circuit=True,
        )

    async def _prepare_initial_runtime_directives(
        self,
        *,
        agent: Any,
        budget: RuntimeBudgetTracker,
        user_message: str,
        stream_callback: Any,
    ) -> tuple[str, AgentResponse | None]:
        effective, count, risk_codes = await self._runtime_directives.prepare_initial(
            agent=agent,
            budget=budget,
            user_message=user_message,
        )
        if risk_codes:
            response = await self._emit_runtime_directive_emergency(
                risk_codes,
                budget=budget,
                stream_callback=stream_callback,
            )
            return effective, response
        if count:
            await self._emit(
                stream_callback,
                "reasoning_summary",
                {
                    "content": "已接收追加要求。正在继续处理…",
                    "status": "running",
                },
            )
        return effective, None

    @staticmethod
    def _skill_metadata(skills: list[Any]) -> dict[str, tuple[str, str]]:
        metadata: dict[str, tuple[str, str]] = {}
        for skill in skills:
            if skill.dir.startswith("skill://") and "@" in skill.dir:
                name, version = skill.dir.removeprefix("skill://").rsplit("@", maxsplit=1)
                metadata[skill.name] = (name, version)
        return metadata

    @staticmethod
    def _skill_result_observer(
        governance: Any,
    ) -> Callable[[str, str, dict[str, JsonValue]], Awaitable[None]]:
        async def observe(
            tool_name: str,
            status: str,
            result_data: dict[str, JsonValue],
        ) -> None:
            skill_id = result_data.get("skill")
            if tool_name == "Skill" and status == "success" and isinstance(skill_id, str):
                await governance.complete_optional_capability_persisted(skill_id)

        return observe

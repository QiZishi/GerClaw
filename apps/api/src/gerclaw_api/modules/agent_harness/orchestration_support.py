"""Focused orchestration support kept outside the bounded composition entry."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agentscope.message import ToolCallBlock
from pydantic import BaseModel

from gerclaw_api.modules.agent_harness.config import ResolvedHarnessConfig
from gerclaw_api.modules.agent_harness.planning import emit_deterministic_clarification
from gerclaw_api.modules.agent_harness.plugin_runtime import (
    ApprovalCallback,
    ApprovalCoordinator,
)
from gerclaw_api.modules.agent_harness.run_lifecycle import bounded_events
from gerclaw_api.modules.agent_harness.run_lifecycle.directive_runtime import (
    RuntimeDirectiveCoordinator,
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
from gerclaw_api.security import JsonValue


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
    ) -> None: ...

    def _bounded_agent_events(
        self,
        events: AsyncIterator[Any],
    ) -> AsyncIterator[Any]:
        return bounded_events(
            events,
            wall_clock_seconds=self._execution_budget.wall_clock_seconds,
            timeout_error_factory=lambda: RuntimeBudgetExceededError(
                "RUNTIME_WALL_CLOCK_EXCEEDED"
            ),
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

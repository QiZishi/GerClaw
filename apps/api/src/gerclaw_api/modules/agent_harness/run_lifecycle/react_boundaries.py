"""Per-step ReAct capacity gates composed from protocol-safe callbacks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from gerclaw_api.modules.agent_harness.run_lifecycle.directive_runtime import (
    DirectiveBudget,
    RuntimeDirectiveCoordinator,
    agent_text_values,
)


class BoundaryDecision(Protocol):
    @property
    def allowed(self) -> bool: ...

    @property
    def reason_code(self) -> str: ...


BoundaryPreflight = Callable[..., BoundaryDecision]
BoundaryErrorFactory = Callable[[str], Exception]
AgentProvider = Callable[[], Any]


class ReActBoundaryCoordinator:
    """Bind directive admission and capacity checks to every ReAct side effect."""

    def __init__(
        self,
        *,
        directives: RuntimeDirectiveCoordinator,
        model_preflight: BoundaryPreflight,
        tool_preflight: BoundaryPreflight,
        error_factory: BoundaryErrorFactory,
        image_count: int,
        tool_result_reserve_tokens: int,
    ) -> None:
        self._directives = directives
        self._model_preflight = model_preflight
        self._tool_preflight = tool_preflight
        self._error_factory = error_factory
        self._image_count = image_count
        self._tool_result_reserve_tokens = tool_result_reserve_tokens

    def bind(
        self,
        *,
        agent_provider: AgentProvider,
        budget: DirectiveBudget,
    ) -> BoundReActBoundaries:
        """Create request-local counters while allowing a repaired Agent replacement."""

        return BoundReActBoundaries(
            coordinator=self,
            agent_provider=agent_provider,
            budget=budget,
        )


@dataclass(slots=True)
class BoundReActBoundaries:
    """Request-local boundary callbacks consumed by the stream projector."""

    coordinator: ReActBoundaryCoordinator
    agent_provider: AgentProvider
    budget: DirectiveBudget
    model_call_count: int = 0

    async def before_model(self) -> int:
        agent = self.agent_provider()
        self.model_call_count += 1
        applied_count = 0
        if self.model_call_count > 1:
            applied_count = await self.coordinator._directives.apply_before_model(
                agent=agent,
                budget=self.budget,
            )
        decision = self.coordinator._model_preflight(
            usage=self.budget.snapshot(),
            text_values=agent_text_values(agent),
            image_count=self.coordinator._image_count,
        )
        if not decision.allowed:
            raise self.coordinator._error_factory(decision.reason_code)
        return applied_count

    async def before_tool(self, tool_name: str) -> None:
        agent = self.agent_provider()
        decision = self.coordinator._tool_preflight(
            usage=self.budget.snapshot(),
            text_values=(*agent_text_values(agent), tool_name),
            image_count=self.coordinator._image_count,
            result_reserve_tokens=self.coordinator._tool_result_reserve_tokens,
        )
        if not decision.allowed:
            raise self.coordinator._error_factory(decision.reason_code)

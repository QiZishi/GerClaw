"""Deterministic checkpoint tracking for the production DynamicPlan."""

from __future__ import annotations

import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from gerclaw_api.modules.agent_harness.planning.clinical_decision import (
    TurnClinicalDecision,
)
from gerclaw_api.modules.agent_harness.planning.contracts import (
    ActionKind,
    DynamicPlan,
    PlanningError,
)
from gerclaw_api.security import JsonValue


class PlanNodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class PlanExecutionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    statuses: dict[str, PlanNodeStatus]


class DynamicPlanExecutor:
    """Advance only declared nodes whose dependencies have completed."""

    def __init__(self, plan: DynamicPlan) -> None:
        self._plan = plan
        self._statuses = {node.node_id: PlanNodeStatus.PENDING for node in plan.nodes}

    def start_capability(self, capability: str) -> str:
        node = next(
            (
                item
                for item in self._plan.nodes
                if item.capability == capability
                and self._statuses[item.node_id] is PlanNodeStatus.PENDING
            ),
            None,
        )
        if node is None:
            raise PlanningError(f"PLAN_CAPABILITY_NOT_PENDING:{capability}")
        incomplete = [
            dependency
            for dependency in node.dependencies
            if self._statuses[dependency] is not PlanNodeStatus.COMPLETED
        ]
        if incomplete:
            raise PlanningError(f"PLAN_DEPENDENCY_INCOMPLETE:{node.node_id}:{','.join(incomplete)}")
        self._statuses[node.node_id] = PlanNodeStatus.RUNNING
        return node.node_id

    def complete(self, node_id: str) -> None:
        if self._statuses.get(node_id) is not PlanNodeStatus.RUNNING:
            raise PlanningError(f"PLAN_NODE_NOT_RUNNING:{node_id}")
        self._statuses[node_id] = PlanNodeStatus.COMPLETED

    def complete_optional_capability(self, capability: str) -> bool:
        """Complete one actually observed optional capability, at most once."""

        node = next(
            (
                item
                for item in self._plan.nodes
                if not item.required
                and item.capability == capability
                and self._statuses[item.node_id] is PlanNodeStatus.PENDING
            ),
            None,
        )
        if node is None:
            return False
        incomplete = [
            dependency
            for dependency in node.dependencies
            if self._statuses[dependency] is not PlanNodeStatus.COMPLETED
        ]
        if incomplete:
            raise PlanningError(f"PLAN_DEPENDENCY_INCOMPLETE:{node.node_id}:{','.join(incomplete)}")
        self._statuses[node.node_id] = PlanNodeStatus.COMPLETED
        return True

    def skip_optional(self) -> None:
        for node in self._plan.nodes:
            if not node.required and self._statuses[node.node_id] is PlanNodeStatus.PENDING:
                self._statuses[node.node_id] = PlanNodeStatus.SKIPPED

    def finalize(self) -> PlanExecutionSnapshot:
        self.skip_optional()
        incomplete = [
            node.node_id
            for node in self._plan.nodes
            if node.required and self._statuses[node.node_id] is not PlanNodeStatus.COMPLETED
        ]
        if incomplete:
            raise PlanningError(f"PLAN_REQUIRED_NODE_INCOMPLETE:{','.join(incomplete)}")
        return self.snapshot()

    def snapshot(self) -> PlanExecutionSnapshot:
        return PlanExecutionSnapshot(statuses=dict(self._statuses))


class TurnExecutionGovernance:
    """Bind SAVI/C3 decisions to actual DynamicPlan checkpoints."""

    def __init__(
        self,
        *,
        plan: DynamicPlan,
        decision: TurnClinicalDecision,
    ) -> None:
        self._plan = plan
        self._decision = decision
        self._executor = DynamicPlanExecutor(plan)

    @property
    def should_ask(self) -> bool:
        selected = self._decision.action_selection.selected
        return selected is not None and selected.candidate.kind is ActionKind.ASK

    def checkpoint(self, capability: str) -> str:
        return self._executor.start_capability(capability)

    def complete(self, node_id: str) -> None:
        self._executor.complete(node_id)

    def complete_optional_capability(self, capability: str) -> bool:
        return self._executor.complete_optional_capability(capability)

    def finish(self) -> dict[str, JsonValue]:
        snapshot = self._executor.finalize()
        return {
            "action_selection": self._decision.action_selection.model_dump(mode="json"),
            "differential_assessment": (
                self._decision.differential_assessment.model_dump(mode="json")
            ),
            "plan_execution": snapshot.model_dump(mode="json"),
        }

    def differential_prompt_context(self) -> tuple[str, str | None]:
        serialized = json.dumps(
            self._decision.differential_assessment.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if not self._decision.differential_assessment.candidates:
            return serialized, None
        return (
            serialized,
            "<code-owned-differential-directions>\n"
            "以下内容是代码校验后的非诊断性方向, 只能据其来源事实说明支持、反对、"
            "残余证据和缺失信息; 不得改写为确诊结论。\n"
            f"{serialized}\n"
            "</code-owned-differential-directions>",
        )

    def clarification_text(self) -> str:
        unknowns = self._decision.clarification_questions[:5]
        if not unknowns:
            raise PlanningError("SAVI_ASK_WITHOUT_UNKNOWNS")
        questions = "\n".join(f"- {item}" for item in unknowns)
        return f"为避免在关键信息不足时直接给出判断或调药建议, 请先补充:\n{questions}"

    def answer_capability(self) -> str:
        for capability in ("answer.quick", "report.compose", "answer.compose"):
            if any(node.capability == capability for node in self._plan.nodes):
                return capability
        raise PlanningError("PLAN_ANSWER_CAPABILITY_MISSING")

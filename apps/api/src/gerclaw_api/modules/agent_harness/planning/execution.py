"""Deterministic checkpoint tracking for the production DynamicPlan."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.modules.agent_harness.planning.clinical_decision import (
    TurnClinicalDecision,
)
from gerclaw_api.modules.agent_harness.planning.contracts import (
    ActionKind,
    DynamicPlan,
    PlanningError,
    PlanNode,
)
from gerclaw_api.security import JsonValue


class PlanNodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanExecutionSnapshot(BaseModel):
    """Content-free, serializable current state for one exact DynamicPlan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["plan-execution-v1"] = "plan-execution-v1"
    statuses: dict[str, PlanNodeStatus]
    attempts: dict[str, int] = Field(default_factory=dict)
    error_codes: dict[str, str] = Field(default_factory=dict)
    fallbacks_used: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_state(self) -> PlanExecutionSnapshot:
        if not 1 <= len(self.statuses) <= 50:
            raise ValueError("plan execution must contain between one and fifty nodes")
        known = set(self.statuses)
        if (
            not set(self.attempts) <= known
            or not set(self.error_codes) <= known
            or not set(self.fallbacks_used) <= known
            or not set(self.fallbacks_used.values()) <= known
        ):
            raise ValueError("plan execution references an unknown node")
        if any(attempt < 0 or attempt > 50 for attempt in self.attempts.values()):
            raise ValueError("plan execution attempt is outside its bound")
        attempted = {
            PlanNodeStatus.RUNNING,
            PlanNodeStatus.COMPLETED,
            PlanNodeStatus.FAILED,
        }
        if any(
            self.attempts.get(node_id, 0) < 1
            for node_id, status in self.statuses.items()
            if status in attempted
        ):
            raise ValueError("active plan execution state requires an attempt")
        if any(
            self.statuses[node_id] is not PlanNodeStatus.FAILED
            for node_id in self.error_codes
        ):
            raise ValueError("only a failed plan node may retain an error code")
        if any(
            re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", code) is None
            for code in self.error_codes.values()
        ):
            raise ValueError("plan execution error code is invalid")
        if any(
            self.statuses[source] is not PlanNodeStatus.FAILED
            for source in self.fallbacks_used
        ):
            raise ValueError("only a failed plan node may use a fallback")
        return self

    @classmethod
    def initial(cls, plan: DynamicPlan) -> PlanExecutionSnapshot:
        return cls(
            statuses={node.node_id: PlanNodeStatus.PENDING for node in plan.nodes},
            attempts={node.node_id: 0 for node in plan.nodes},
        )

    def validate_for(self, plan: DynamicPlan) -> PlanExecutionSnapshot:
        expected = {node.node_id for node in plan.nodes}
        if set(self.statuses) != expected or set(self.attempts) != expected:
            raise PlanningError("PLAN_EXECUTION_SNAPSHOT_MISMATCH")
        declared_fallbacks = {
            node.node_id: set(node.fallback)
            for node in plan.nodes
        }
        if any(
            fallback_id not in declared_fallbacks[source_id]
            for source_id, fallback_id in self.fallbacks_used.items()
        ):
            raise PlanningError("PLAN_EXECUTION_FALLBACK_MISMATCH")
        return self


class DynamicPlanExecutor:
    """Advance only declared nodes whose dependencies have completed."""

    def __init__(
        self,
        plan: DynamicPlan,
        *,
        snapshot: PlanExecutionSnapshot | None = None,
    ) -> None:
        self._plan = plan
        restored = (snapshot or PlanExecutionSnapshot.initial(plan)).validate_for(plan)
        self._statuses = dict(restored.statuses)
        self._attempts = dict(restored.attempts)
        self._error_codes = dict(restored.error_codes)
        self._fallbacks_used = dict(restored.fallbacks_used)

    def start_capability(self, capability: str) -> str:
        node = next(
            (
                item
                for item in self._plan.nodes
                if item.capability == capability
                and self._statuses[item.node_id]
                in {PlanNodeStatus.PENDING, PlanNodeStatus.FAILED}
            ),
            None,
        )
        if node is None:
            raise PlanningError(f"PLAN_CAPABILITY_NOT_PENDING:{capability}")
        incomplete = [
            dependency
            for dependency in node.dependencies
            if not self._satisfied(dependency)
        ]
        if incomplete:
            raise PlanningError(f"PLAN_DEPENDENCY_INCOMPLETE:{node.node_id}:{','.join(incomplete)}")
        self._statuses[node.node_id] = PlanNodeStatus.RUNNING
        self._attempts[node.node_id] += 1
        self._error_codes.pop(node.node_id, None)
        self._fallbacks_used.pop(node.node_id, None)
        return node.node_id

    def complete(self, node_id: str) -> None:
        if self._statuses.get(node_id) is not PlanNodeStatus.RUNNING:
            raise PlanningError(f"PLAN_NODE_NOT_RUNNING:{node_id}")
        self._statuses[node_id] = PlanNodeStatus.COMPLETED
        self._error_codes.pop(node_id, None)

    def fail(self, node_id: str, error_code: str) -> tuple[str, ...]:
        if self._statuses.get(node_id) is not PlanNodeStatus.RUNNING:
            raise PlanningError(f"PLAN_NODE_NOT_RUNNING:{node_id}")
        if re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", error_code) is None:
            raise PlanningError("PLAN_NODE_ERROR_CODE_INVALID")
        self._statuses[node_id] = PlanNodeStatus.FAILED
        self._error_codes[node_id] = error_code
        node = self._node(node_id)
        return tuple(
            fallback_id
            for fallback_id in node.fallback
            if self._statuses[fallback_id]
            in {PlanNodeStatus.PENDING, PlanNodeStatus.FAILED}
            and all(self._satisfied(item) for item in self._node(fallback_id).dependencies)
        )

    def start_fallback(self, failed_node_id: str) -> str:
        if self._statuses.get(failed_node_id) is not PlanNodeStatus.FAILED:
            raise PlanningError(f"PLAN_NODE_NOT_FAILED:{failed_node_id}")
        available = self.failover_candidates(failed_node_id)
        if not available:
            raise PlanningError(f"PLAN_FALLBACK_UNAVAILABLE:{failed_node_id}")
        fallback_id = available[0]
        self._statuses[fallback_id] = PlanNodeStatus.RUNNING
        self._attempts[fallback_id] += 1
        self._error_codes.pop(fallback_id, None)
        self._fallbacks_used[failed_node_id] = fallback_id
        return fallback_id

    def failover_candidates(self, failed_node_id: str) -> tuple[str, ...]:
        if self._statuses.get(failed_node_id) is not PlanNodeStatus.FAILED:
            return ()
        node = self._node(failed_node_id)
        return tuple(
            fallback_id
            for fallback_id in node.fallback
            if self._statuses[fallback_id]
            in {PlanNodeStatus.PENDING, PlanNodeStatus.FAILED}
            and all(self._satisfied(item) for item in self._node(fallback_id).dependencies)
        )

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
            if not self._satisfied(dependency)
        ]
        if incomplete:
            raise PlanningError(f"PLAN_DEPENDENCY_INCOMPLETE:{node.node_id}:{','.join(incomplete)}")
        self._attempts[node.node_id] += 1
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
            if node.required and not self._satisfied(node.node_id)
        ]
        if incomplete:
            raise PlanningError(f"PLAN_REQUIRED_NODE_INCOMPLETE:{','.join(incomplete)}")
        return self.snapshot()

    def snapshot(self) -> PlanExecutionSnapshot:
        return PlanExecutionSnapshot(
            statuses=dict(self._statuses),
            attempts=dict(self._attempts),
            error_codes=dict(self._error_codes),
            fallbacks_used=dict(self._fallbacks_used),
        )

    def _node(self, node_id: str) -> PlanNode:
        return next(node for node in self._plan.nodes if node.node_id == node_id)

    def _satisfied(self, node_id: str, *, visited: frozenset[str] = frozenset()) -> bool:
        if node_id in visited:
            return False
        if self._statuses[node_id] is PlanNodeStatus.COMPLETED:
            return True
        fallback_id = self._fallbacks_used.get(node_id)
        return (
            self._statuses[node_id] is PlanNodeStatus.FAILED
            and fallback_id is not None
            and self._satisfied(fallback_id, visited=visited | {node_id})
        )


class TurnExecutionGovernance:
    """Bind SAVI/C3 decisions to actual DynamicPlan checkpoints."""

    def __init__(
        self,
        *,
        plan: DynamicPlan,
        decision: TurnClinicalDecision,
        execution_snapshot: PlanExecutionSnapshot | None = None,
    ) -> None:
        self._plan = plan
        self._decision = decision
        self._executor = DynamicPlanExecutor(plan, snapshot=execution_snapshot)

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

    def fail(self, node_id: str, error_code: str) -> tuple[str, ...]:
        return self._executor.fail(node_id, error_code)

    def start_fallback(self, failed_node_id: str) -> str:
        return self._executor.start_fallback(failed_node_id)

    def snapshot(self) -> PlanExecutionSnapshot:
        return self._executor.snapshot()

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

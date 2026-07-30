"""Deterministic checkpoint tracking for the production DynamicPlan."""

from __future__ import annotations

import hashlib
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
    plan_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    statuses: dict[str, PlanNodeStatus]
    attempts: dict[str, int] = Field(default_factory=dict)
    error_codes: dict[str, str] = Field(default_factory=dict)
    fallbacks_used: dict[str, tuple[str, ...]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_state(self) -> PlanExecutionSnapshot:
        if not 1 <= len(self.statuses) <= 50:
            raise ValueError("plan execution must contain between one and fifty nodes")
        known = set(self.statuses)
        if (
            not set(self.attempts) <= known
            or not set(self.error_codes) <= known
            or not set(self.fallbacks_used) <= known
            or not {
                fallback_id
                for fallback_ids in self.fallbacks_used.values()
                for fallback_id in fallback_ids
            }
            <= known
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
        failed = {
            node_id
            for node_id, status in self.statuses.items()
            if status is PlanNodeStatus.FAILED
        }
        if set(self.error_codes) != failed:
            raise ValueError("every failed plan node requires exactly one error code")
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
        if any(
            not fallback_ids or len(set(fallback_ids)) != len(fallback_ids)
            for fallback_ids in self.fallbacks_used.values()
        ):
            raise ValueError("plan fallback history must be non-empty and unique")
        return self

    @classmethod
    def initial(cls, plan: DynamicPlan) -> PlanExecutionSnapshot:
        return cls(
            plan_fingerprint=_plan_fingerprint(plan),
            statuses={node.node_id: PlanNodeStatus.PENDING for node in plan.nodes},
            attempts={node.node_id: 0 for node in plan.nodes},
        )

    def validate_for(self, plan: DynamicPlan) -> PlanExecutionSnapshot:
        expected = {node.node_id for node in plan.nodes}
        if (
            self.plan_fingerprint != _plan_fingerprint(plan)
            or set(self.statuses) != expected
            or set(self.attempts) != expected
        ):
            raise PlanningError("PLAN_EXECUTION_SNAPSHOT_MISMATCH")
        declared_fallbacks = {
            node.node_id: node.fallback
            for node in plan.nodes
        }
        if any(
            fallback_ids != declared_fallbacks[source_id][: len(fallback_ids)]
            or any(
                self.attempts[fallback_id] < 1
                or self.statuses[fallback_id]
                not in {
                    PlanNodeStatus.RUNNING,
                    PlanNodeStatus.COMPLETED,
                    PlanNodeStatus.FAILED,
                }
                for fallback_id in fallback_ids
            )
            or any(
                self.statuses[fallback_id] is not PlanNodeStatus.FAILED
                for fallback_id in fallback_ids[:-1]
            )
            for source_id, fallback_ids in self.fallbacks_used.items()
        ):
            raise PlanningError("PLAN_EXECUTION_FALLBACK_MISMATCH")
        return self


class PlanExecutionTransition(BaseModel):
    """One validated content-free delta ready for Run Lifecycle persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    previous_status: PlanNodeStatus
    status: PlanNodeStatus
    attempt: int = Field(ge=0, le=50)
    error_code: str | None = None
    fallback_for_node_id: str | None = None


def validate_plan_execution_transition(
    plan: DynamicPlan,
    current: PlanExecutionSnapshot,
    updated: PlanExecutionSnapshot,
) -> tuple[PlanExecutionTransition, ...]:
    """Expand one legal persisted delta into its content-free node transitions."""

    current.validate_for(plan)
    updated.validate_for(plan)
    node_by_id = {node.node_id: node for node in plan.nodes}
    changed_nodes = [
        node_id
        for node_id in current.statuses
        if current.statuses[node_id] is not updated.statuses[node_id]
    ]
    if not changed_nodes:
        raise PlanningError("PLAN_EXECUTION_TRANSITION_NOT_ATOMIC")
    if len(changed_nodes) > 1:
        if (
            current.attempts != updated.attempts
            or current.error_codes != updated.error_codes
            or current.fallbacks_used != updated.fallbacks_used
            or any(
                node_by_id[node_id].required
                or current.statuses[node_id] is not PlanNodeStatus.PENDING
                or updated.statuses[node_id] is not PlanNodeStatus.SKIPPED
                for node_id in changed_nodes
            )
        ):
            raise PlanningError("PLAN_EXECUTION_TRANSITION_NOT_ATOMIC")
        return tuple(
            PlanExecutionTransition(
                node_id=node.node_id,
                previous_status=PlanNodeStatus.PENDING,
                status=PlanNodeStatus.SKIPPED,
                attempt=updated.attempts[node.node_id],
            )
            for node in plan.nodes
            if node.node_id in changed_nodes
        )
    node_id = changed_nodes[0]
    node = node_by_id[node_id]
    previous_status = current.statuses[node_id]
    status = updated.statuses[node_id]
    current_attempt = current.attempts[node_id]
    attempt = updated.attempts[node_id]
    changed_attempts = {
        item for item in current.attempts if current.attempts[item] != updated.attempts[item]
    }
    changed_errors = {
        item
        for item in set(current.error_codes) | set(updated.error_codes)
        if current.error_codes.get(item) != updated.error_codes.get(item)
    }
    if not changed_attempts <= {node_id} or not changed_errors <= {node_id}:
        raise PlanningError("PLAN_EXECUTION_TRANSITION_DRIFT")

    changed_fallbacks = {
        source
        for source in set(current.fallbacks_used) | set(updated.fallbacks_used)
        if current.fallbacks_used.get(source) != updated.fallbacks_used.get(source)
    }
    fallback_for_node_id: str | None = None
    if len(changed_fallbacks) > 1:
        raise PlanningError("PLAN_EXECUTION_TRANSITION_DRIFT")
    if changed_fallbacks:
        source = next(iter(changed_fallbacks))
        before = current.fallbacks_used.get(source, ())
        after = updated.fallbacks_used.get(source, ())
        if (
            len(after) == len(before) + 1
            and after[:-1] == before
            and after[-1] == node_id
            and current.statuses[source] is PlanNodeStatus.FAILED
            and previous_status is PlanNodeStatus.PENDING
            and status is PlanNodeStatus.RUNNING
        ):
            fallback_for_node_id = source
        else:
            raise PlanningError("PLAN_EXECUTION_FALLBACK_MISMATCH")

    allowed = False
    if (
        previous_status in {PlanNodeStatus.PENDING, PlanNodeStatus.FAILED}
        and status is PlanNodeStatus.RUNNING
    ):
        allowed = (
            attempt == current_attempt + 1
            and node_id not in updated.error_codes
            and all(
                _snapshot_satisfied(current, dependency)
                for dependency in node.dependencies
            )
        )
    elif previous_status is PlanNodeStatus.RUNNING and status in {
        PlanNodeStatus.COMPLETED,
        PlanNodeStatus.FAILED,
    }:
        allowed = attempt == current_attempt
        if status is PlanNodeStatus.FAILED:
            allowed = allowed and node_id in updated.error_codes
        else:
            allowed = allowed and node_id not in updated.error_codes
    elif previous_status is PlanNodeStatus.PENDING and status is PlanNodeStatus.COMPLETED:
        allowed = (
            not node.required
            and not changed_fallbacks
            and attempt == current_attempt + 1
            and node_id not in updated.error_codes
            and all(
                _snapshot_satisfied(current, dependency)
                for dependency in node.dependencies
            )
        )
    elif previous_status is PlanNodeStatus.PENDING and status is PlanNodeStatus.SKIPPED:
        allowed = (
            not node.required
            and attempt == current_attempt
            and node_id not in updated.error_codes
        )
    if not allowed:
        raise PlanningError(
            f"PLAN_EXECUTION_TRANSITION_INVALID:{node_id}:{previous_status}:{status}"
        )
    return (
        PlanExecutionTransition(
            node_id=node_id,
            previous_status=previous_status,
            status=status,
            attempt=attempt,
            error_code=updated.error_codes.get(node_id),
            fallback_for_node_id=fallback_for_node_id,
        ),
    )


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
        self._plan_fingerprint = restored.plan_fingerprint
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
                and not self._satisfied(item.node_id)
                and not self._fallbacks_used.get(item.node_id)
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
        self._require_attempt_capacity(node.node_id)
        self._statuses[node.node_id] = PlanNodeStatus.RUNNING
        self._attempts[node.node_id] += 1
        self._error_codes.pop(node.node_id, None)
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
        return self.failover_candidates(node_id)

    def start_fallback(self, failed_node_id: str) -> str:
        if self._statuses.get(failed_node_id) is not PlanNodeStatus.FAILED:
            raise PlanningError(f"PLAN_NODE_NOT_FAILED:{failed_node_id}")
        available = self.failover_candidates(failed_node_id)
        if not available:
            raise PlanningError(f"PLAN_FALLBACK_UNAVAILABLE:{failed_node_id}")
        fallback_id = available[0]
        self._require_attempt_capacity(fallback_id)
        self._statuses[fallback_id] = PlanNodeStatus.RUNNING
        self._attempts[fallback_id] += 1
        self._error_codes.pop(fallback_id, None)
        self._fallbacks_used[failed_node_id] = (
            *self._fallbacks_used.get(failed_node_id, ()),
            fallback_id,
        )
        return fallback_id

    def failover_candidates(self, failed_node_id: str) -> tuple[str, ...]:
        if self._statuses.get(failed_node_id) is not PlanNodeStatus.FAILED:
            return ()
        node = self._node(failed_node_id)
        used = self._fallbacks_used.get(failed_node_id, ())
        if used and self._statuses[used[-1]] is not PlanNodeStatus.FAILED:
            return ()
        if len(used) >= len(node.fallback):
            return ()
        fallback_id = node.fallback[len(used)]
        if self._statuses[fallback_id] is not PlanNodeStatus.PENDING:
            return ()
        if not all(
            self._satisfied(item) for item in self._node(fallback_id).dependencies
        ):
            return ()
        return (fallback_id,)

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
        self._require_attempt_capacity(node.node_id)
        self._attempts[node.node_id] += 1
        self._statuses[node.node_id] = PlanNodeStatus.COMPLETED
        return True

    def skip_optional(self) -> None:
        for node in self._plan.nodes:
            if not node.required and self._statuses[node.node_id] is PlanNodeStatus.PENDING:
                self._statuses[node.node_id] = PlanNodeStatus.SKIPPED

    def finalize(self) -> PlanExecutionSnapshot:
        incomplete = [
            node.node_id
            for node in self._plan.nodes
            if node.required and not self._satisfied(node.node_id)
        ]
        if incomplete:
            raise PlanningError(f"PLAN_REQUIRED_NODE_INCOMPLETE:{','.join(incomplete)}")
        self.skip_optional()
        return self.snapshot()

    def snapshot(self) -> PlanExecutionSnapshot:
        return PlanExecutionSnapshot(
            plan_fingerprint=self._plan_fingerprint,
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
        fallback_ids = self._fallbacks_used.get(node_id, ())
        return (
            self._statuses[node_id] is PlanNodeStatus.FAILED
            and bool(fallback_ids)
            and any(
                self._satisfied(fallback_id, visited=visited | {node_id})
                for fallback_id in fallback_ids
            )
        )

    def _require_attempt_capacity(self, node_id: str) -> None:
        if self._attempts[node_id] >= 50:
            raise PlanningError(f"PLAN_NODE_ATTEMPT_BUDGET_EXCEEDED:{node_id}")


def _plan_fingerprint(plan: DynamicPlan) -> str:
    canonical = json.dumps(
        plan.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _snapshot_satisfied(
    snapshot: PlanExecutionSnapshot,
    node_id: str,
    *,
    visited: frozenset[str] = frozenset(),
) -> bool:
    if node_id in visited:
        return False
    if snapshot.statuses[node_id] is PlanNodeStatus.COMPLETED:
        return True
    return (
        snapshot.statuses[node_id] is PlanNodeStatus.FAILED
        and any(
            _snapshot_satisfied(
                snapshot,
                fallback_id,
                visited=visited | {node_id},
            )
            for fallback_id in snapshot.fallbacks_used.get(node_id, ())
        )
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

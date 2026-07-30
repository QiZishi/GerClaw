"""Versioned DAG planning contracts independent of concrete capabilities."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.security import JsonValue


class PlanningError(RuntimeError):
    """Stable plan construction failure."""


class PlanNodeBudget(BaseModel):
    """Per-node declared resource ceiling, never an accounting authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_calls: int = Field(default=0, ge=0, le=50)
    tool_calls: int = Field(default=0, ge=0, le=50)
    input_tokens: int = Field(default=0, ge=0, le=1_000_000)
    output_tokens: int = Field(default=0, ge=0, le=100_000)


class PlanNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    required: bool = True
    dependencies: tuple[str, ...] = Field(default=(), max_length=20)
    capability: str = Field(min_length=1, max_length=128)
    budget: PlanNodeBudget = Field(default_factory=PlanNodeBudget)
    public_summary: str = Field(min_length=1, max_length=240)
    output_schema: dict[str, JsonValue] = Field(default_factory=dict)
    fallback: tuple[str, ...] = Field(default=(), max_length=10)
    checkpoint: bool = False

    @model_validator(mode="after")
    def reject_self_reference(self) -> PlanNode:
        if self.node_id in self.dependencies or self.node_id in self.fallback:
            raise ValueError("plan node cannot depend on or fall back to itself")
        if len(self.fallback) != len(set(self.fallback)):
            raise ValueError("plan node fallback entries must be unique")
        return self


class DynamicPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    route: RouteKind = RouteKind.STANDARD
    nodes: tuple[PlanNode, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_graph_references(self) -> DynamicPlan:
        ids = [node.node_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("plan node ids must be unique")
        known = set(ids)
        referenced = {
            reference for node in self.nodes for reference in (*node.dependencies, *node.fallback)
        }
        if unknown := referenced - known:
            raise ValueError(f"plan references unknown nodes: {sorted(unknown)}")
        node_by_id = {node.node_id: node for node in self.nodes}
        fallback_target_ids = {fallback_id for node in self.nodes for fallback_id in node.fallback}
        if any(node_by_id[fallback_id].required for fallback_id in fallback_target_ids):
            raise ValueError("plan fallback target must be optional")
        if any(
            dependency in fallback_target_ids
            for node in self.nodes
            for dependency in node.dependencies
        ):
            raise ValueError("plan fallback target cannot be a dependency")
        fallback_owners: dict[str, str] = {}
        for node in self.nodes:
            for fallback_id in node.fallback:
                owner = fallback_owners.setdefault(fallback_id, node.node_id)
                if owner != node.node_id:
                    raise ValueError("plan fallback node must have exactly one source owner")
        references = {
            node.node_id: set((*node.dependencies, *node.fallback)) for node in self.nodes
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("plan dependency graph must be acyclic")
            if node_id in visited:
                return
            visiting.add(node_id)
            for reference in references[node_id]:
                visit(reference)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in ids:
            visit(node_id)
        return self


class PlanRequest(BaseModel):
    """Validated facts that may change plan shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    route: RouteKind
    medical_content: bool = False
    image_count: int = Field(default=0, ge=0, le=10)
    document_count: int = Field(default=0, ge=0, le=10)
    selected_capabilities: tuple[str, ...] = Field(default=(), max_length=50)
    available_capabilities: tuple[str, ...] = Field(default=(), max_length=100)
    report_requested: bool = False
    selected_action: Literal["ask", "exam", "answer"] = "answer"


class Planner(Protocol):
    def build(self, request: PlanRequest) -> DynamicPlan:
        """Build a bounded DAG without executing its nodes."""


class ActionKind(StrEnum):
    ASK = "ask"
    EXAM = "exam"
    ANSWER = "answer"


class ActionCandidate(BaseModel):
    """One code-rankable action using ordinal, not probabilistic, values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    kind: ActionKind
    public_summary: str = Field(min_length=1, max_length=240)
    hypothesis_links: tuple[str, ...] = Field(default=(), max_length=20)
    safety_required: bool = False
    treatment_prerequisite: bool = False
    already_known: bool = False
    catalog_valid: bool = True
    diagnostic_gain: int = Field(default=0, ge=0, le=3)
    comorbidity_gain: int = Field(default=0, ge=0, le=3)
    treatment_gain: int = Field(default=0, ge=0, le=3)
    safety_gain: int = Field(default=0, ge=0, le=3)
    token_cost: int = Field(default=0, ge=0, le=3)
    action_cost: int = Field(default=0, ge=0, le=3)
    invasiveness: int = Field(default=0, ge=0, le=3)
    redundancy: int = Field(default=0, ge=0, le=3)

    @model_validator(mode="after")
    def require_decision_link(self) -> ActionCandidate:
        if (
            self.kind is not ActionKind.ANSWER
            and not self.safety_required
            and not self.treatment_prerequisite
            and not self.hypothesis_links
        ):
            raise ValueError("ASK/EXAM action requires a clinical decision link")
        return self


class RankedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: ActionCandidate
    score: int = Field(ge=-12, le=12)


class ActionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selected: RankedAction | None = None
    rejected_action_ids: tuple[str, ...] = Field(default=(), max_length=50)
    should_stop: bool
    reason_code: str = Field(min_length=1, max_length=64)


class ModelCallEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    estimated_input_tokens: int = Field(ge=0, le=1_000_000)
    output_reserve_tokens: int = Field(ge=1, le=100_000)
    additional_model_calls: int = Field(default=1, ge=1, le=50)
    additional_tool_calls: int = Field(default=0, ge=0, le=50)


class BudgetPreflightDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    reason_code: str = Field(min_length=1, max_length=64)
    estimated_input_tokens: int = Field(ge=0)
    output_reserve_tokens: int = Field(ge=1)

"""Versioned DAG planning contracts independent of concrete capabilities."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.security import JsonValue


class PlanningError(RuntimeError):
    """Stable plan construction failure."""


class PlanNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    required: bool = True
    dependencies: tuple[str, ...] = Field(default=(), max_length=20)
    capability: str = Field(min_length=1, max_length=128)
    budget: dict[str, JsonValue] = Field(default_factory=dict)
    public_summary: str = Field(min_length=1, max_length=240)
    output_schema: dict[str, JsonValue] = Field(default_factory=dict)
    fallback: tuple[str, ...] = Field(default=(), max_length=10)
    checkpoint: bool = False

    @model_validator(mode="after")
    def reject_self_reference(self) -> PlanNode:
        if self.node_id in self.dependencies or self.node_id in self.fallback:
            raise ValueError("plan node cannot depend on or fall back to itself")
        return self


class DynamicPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    nodes: tuple[PlanNode, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_graph_references(self) -> DynamicPlan:
        ids = [node.node_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("plan node ids must be unique")
        known = set(ids)
        referenced = {
            reference
            for node in self.nodes
            for reference in (*node.dependencies, *node.fallback)
        }
        if unknown := referenced - known:
            raise ValueError(f"plan references unknown nodes: {sorted(unknown)}")
        dependencies = {node.node_id: set(node.dependencies) for node in self.nodes}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("plan dependency graph must be acyclic")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in dependencies[node_id]:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in ids:
            visit(node_id)
        return self


class Planner(Protocol):
    def build(self, *, capabilities: tuple[str, ...]) -> DynamicPlan:
        """Build a bounded DAG without executing its nodes."""

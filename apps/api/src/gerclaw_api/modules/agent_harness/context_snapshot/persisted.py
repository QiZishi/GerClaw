"""Encrypted-at-rest contracts required to resume one exact Agent turn."""

from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gerclaw_api.modules.agent_harness.config import ResolvedHarnessConfig
from gerclaw_api.modules.agent_harness.context_snapshot.models import AgentContext
from gerclaw_api.modules.agent_harness.planning.clinical_decision import (
    TurnClinicalDecision,
)
from gerclaw_api.modules.agent_harness.planning.contracts import DynamicPlan, PlanningError
from gerclaw_api.modules.agent_harness.planning.execution import PlanExecutionSnapshot
from gerclaw_api.modules.agent_harness.plugin_runtime.contracts import (
    CapabilityResult,
    CapabilitySelection,
)
from gerclaw_api.modules.agent_harness.routing.contracts import RouteDecision
from gerclaw_api.modules.document.models import UploadedDocumentContext
from gerclaw_api.modules.runtime.models import ExecutionBudget
from gerclaw_api.modules.skill.models import SkillDefinition, SkillId
from gerclaw_api.modules.workflows.models import WorkflowDefinition, WorkflowId

_FINGERPRINT_PATTERN = r"^[a-f0-9]{64}$"


class FrozenToolContract(BaseModel):
    """One model-visible tool name bound to its immutable Runtime contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{1,63}$")
    version: str = Field(pattern=r"^[1-9][0-9]{0,3}\.[0-9]{1,4}\.[0-9]{1,4}$")


class PersistedContextSnapshot(BaseModel):
    """Frozen model-visible inputs and validated reusable assets for one Run.

    The enclosing ``AgentRun.context_snapshot`` column is encrypted. This
    contract deliberately excludes provider credentials, raw provider
    payloads, private reasoning, and mutable authorization decisions.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["context-snapshot-v2"] = "context-snapshot-v2"
    input_message_id: uuid.UUID
    agent_context: AgentContext
    prompt_policy_ids: tuple[str, ...] = Field(default=(), max_length=20)
    tool_contracts: tuple[FrozenToolContract, ...] = Field(default=(), max_length=100)
    skill_definitions: tuple[SkillDefinition, ...] = Field(default=(), max_length=20)
    uploaded_documents: tuple[UploadedDocumentContext, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def validate_asset_identity(self) -> PersistedContextSnapshot:
        if self.agent_context.projection is None:
            raise ValueError("snapshot is missing its frozen context projection")
        if self.prompt_policy_ids != self.agent_context.system_instructions:
            raise ValueError("snapshot Prompt policy ids do not match Agent context")
        if tuple(item.name for item in self.tool_contracts) != (self.agent_context.tool_names):
            raise ValueError("snapshot tool contracts do not match Agent context")
        skill_ids = tuple(item.skill_id for item in self.skill_definitions)
        if skill_ids != tuple(self.agent_context.loaded_skills):
            raise ValueError("snapshot Skill definitions do not match Agent context")
        document_ids = tuple(str(item.document_id) for item in self.uploaded_documents)
        if document_ids != tuple(self.agent_context.uploaded_files):
            raise ValueError("snapshot documents do not match Agent context")
        return self


class PersistedRunPlan(BaseModel):
    """Frozen deterministic decisions and budgets for one resumable Run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["run-plan-v1"] = "run-plan-v1"
    loaded_skill_count: int = Field(ge=0, le=20)
    loaded_skill_ids: tuple[SkillId, ...] = Field(default=(), max_length=20)
    requested_capability_count: int = Field(default=0, ge=0, le=20)
    requested_capability_ids: tuple[str, ...] = Field(default=(), max_length=20)
    capability_selection: CapabilitySelection = Field(default_factory=CapabilitySelection)
    capability_results: tuple[CapabilityResult, ...] = Field(default=(), max_length=20)
    uploaded_document_count: int = Field(ge=0, le=10)
    uploaded_document_ids: tuple[uuid.UUID, ...] = Field(default=(), max_length=10)
    uploaded_image_count: int = Field(ge=0, le=10)
    uploaded_image_fingerprints: tuple[str, ...] = Field(default=(), max_length=10)
    workflow: WorkflowId
    workflow_definition: WorkflowDefinition
    channel: Literal["web", "voice"] = "web"
    workflow_version: str = Field(pattern=r"^[1-9][0-9]{0,3}\.[0-9]{1,4}\.[0-9]{1,4}$")
    workflow_owner_module: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    search_enabled: bool
    route_decision: RouteDecision
    dynamic_plan: DynamicPlan
    plan_execution: PlanExecutionSnapshot | None = None
    clinical_decision: TurnClinicalDecision
    resolved_config: ResolvedHarnessConfig
    execution_budget: ExecutionBudget
    regenerate_from_run_id: uuid.UUID | None = None
    expected_current_answer_version_id: uuid.UUID | None = None

    @field_validator("uploaded_image_fingerprints")
    @classmethod
    def validate_image_fingerprints(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(re.fullmatch(_FINGERPRINT_PATTERN, item) is None for item in value):
            raise ValueError("run plan contains an invalid image fingerprint")
        return value

    @model_validator(mode="after")
    def validate_identity(self) -> PersistedRunPlan:
        if (
            self.loaded_skill_count != len(self.loaded_skill_ids)
            or self.requested_capability_count != len(self.requested_capability_ids)
            or self.uploaded_document_count != len(self.uploaded_document_ids)
            or self.uploaded_image_count != len(self.uploaded_image_fingerprints)
        ):
            raise ValueError("run plan counts do not match stored identifiers")
        if len(set(self.loaded_skill_ids)) != len(self.loaded_skill_ids):
            raise ValueError("run plan contains duplicate Skill ids")
        if len(set(self.requested_capability_ids)) != len(self.requested_capability_ids):
            raise ValueError("run plan contains duplicate capability ids")
        if len(set(self.uploaded_document_ids)) != len(self.uploaded_document_ids):
            raise ValueError("run plan contains duplicate document ids")
        if (self.regenerate_from_run_id is None) != (
            self.expected_current_answer_version_id is None
        ):
            raise ValueError("run plan regeneration identifiers must be paired")
        if self.route_decision.route is not self.dynamic_plan.route:
            raise ValueError("route decision and dynamic plan route must match")
        if self.plan_execution is not None:
            try:
                self.plan_execution.validate_for(self.dynamic_plan)
            except PlanningError as error:
                raise ValueError("plan execution does not match dynamic plan") from error
        if (
            self.workflow_definition.workflow_id is not self.workflow
            or self.workflow_definition.version != self.workflow_version
            or self.workflow_definition.owner_module != self.workflow_owner_module
            or self.workflow_definition.search_enabled is not self.search_enabled
        ):
            raise ValueError("run plan workflow metadata is inconsistent")
        selected_ids = self.capability_selection.ids
        if any(result.capability_id not in selected_ids for result in self.capability_results):
            raise ValueError("capability result is not part of the frozen selection")
        return self

    def effective_plan_execution(self) -> PlanExecutionSnapshot:
        """Restore legacy plans as all-pending without mutating their frozen payload."""

        return self.plan_execution or PlanExecutionSnapshot.initial(self.dynamic_plan)


class FrozenRunState(BaseModel):
    """Cross-validated context and plan returned only by the resume boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot: PersistedContextSnapshot
    plan: PersistedRunPlan

    @model_validator(mode="after")
    def validate_cross_contract_identity(self) -> FrozenRunState:
        context = self.snapshot.agent_context
        effective_skills = (
            ()
            if self.plan.route_decision.route.value == "emergency"
            else self.plan.loaded_skill_ids
        )
        effective_documents = (
            ()
            if self.plan.route_decision.route.value == "emergency"
            else tuple(str(item) for item in self.plan.uploaded_document_ids)
        )
        if tuple(context.loaded_skills) != tuple(effective_skills):
            raise ValueError("snapshot and plan Skill identities do not match")
        if tuple(context.uploaded_files) != effective_documents:
            raise ValueError("snapshot and plan document identities do not match")
        return self


class ControlledSuccessorState(BaseModel):
    """Frozen source inputs plus the directive that creates a new fenced Run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_run_id: uuid.UUID
    source_trace_id: str = Field(pattern=r"^trace_[A-Za-z0-9][A-Za-z0-9_.:-]{7,57}$")
    directive_id: uuid.UUID
    source: FrozenRunState

    @model_validator(mode="after")
    def validate_source_trace_identity(self) -> ControlledSuccessorState:
        if self.source.snapshot.agent_context.execution.trace_id != self.source_trace_id:
            raise ValueError("controlled successor source Trace does not match snapshot")
        return self

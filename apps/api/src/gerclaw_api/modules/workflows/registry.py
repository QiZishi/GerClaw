"""Fail-closed registry for actual Runtime workflows."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from gerclaw_api.modules.runtime.models import DataClass, NetworkAccess, RiskLevel
from gerclaw_api.modules.security_evaluation import SecurityEvaluationError, SecurityProfileRegistry
from gerclaw_api.modules.workflows.models import (
    WorkflowContextError,
    WorkflowDefinition,
    WorkflowId,
)
from gerclaw_api.modules.workflows.profiles import build_workflow_security_registry

WORKFLOW_DEFINITIONS: tuple[WorkflowDefinition, ...] = (
    WorkflowDefinition(
        workflow_id=WorkflowId.STANDARD,
        version="1.0.0",
        owner_module="agent_harness",
        description="Evidence-backed geriatric consultation through the governed Agent Harness.",
        risk_level=RiskLevel.MEDIUM,
        network_access=NetworkAccess.EXTERNAL,
        data_classes=frozenset({DataClass.INTERNAL, DataClass.PHI}),
        accepts_skills=True,
        accepts_uploaded_files=True,
        search_enabled=True,
    ),
    WorkflowDefinition(
        workflow_id=WorkflowId.CGA,
        version="1.0.0",
        owner_module="cga",
        description=(
            "Bounded CGA-assistance conversation; scoring remains in the deterministic CGA module."
        ),
        risk_level=RiskLevel.MEDIUM,
        network_access=NetworkAccess.INTERNAL,
        data_classes=frozenset({DataClass.INTERNAL, DataClass.PHI}),
        accepts_skills=True,
        accepts_uploaded_files=True,
        search_enabled=False,
    ),
    WorkflowDefinition(
        workflow_id=WorkflowId.COMPANION,
        version="1.0.0",
        owner_module="companion",
        description=(
            "Isolated emotional-companion conversation without retrieval "
            "or persistent health memory."
        ),
        risk_level=RiskLevel.MEDIUM,
        network_access=NetworkAccess.NONE,
        data_classes=frozenset({DataClass.INTERNAL}),
        accepts_skills=False,
        accepts_uploaded_files=False,
        search_enabled=False,
    ),
    WorkflowDefinition(
        workflow_id=WorkflowId.PRESCRIPTION,
        version="1.0.0",
        owner_module="prescription",
        description=(
            "Evidence-bound five-prescription draft generation with private uploaded input "
            "and mandatory clinician review."
        ),
        risk_level=RiskLevel.HIGH,
        network_access=NetworkAccess.EXTERNAL,
        data_classes=frozenset({DataClass.INTERNAL, DataClass.PHI}),
        accepts_skills=False,
        accepts_uploaded_files=True,
        search_enabled=True,
    ),
)


class WorkflowRegistry:
    """Resolve only reviewed workflow definitions and their risk profiles."""

    def __init__(
        self,
        definitions: Iterable[WorkflowDefinition] = WORKFLOW_DEFINITIONS,
        *,
        security_profiles: SecurityProfileRegistry | None = None,
    ) -> None:
        self._definitions: dict[WorkflowId, WorkflowDefinition] = {}
        for definition in definitions:
            if definition.workflow_id in self._definitions:
                raise ValueError(f"duplicate workflow registration: {definition.workflow_id}")
            self._definitions[definition.workflow_id] = definition
        self._security_profiles = security_profiles or build_workflow_security_registry()

    def resolve(self, workflow_id: WorkflowId | str) -> WorkflowDefinition:
        try:
            normalized = WorkflowId(workflow_id)
        except ValueError as error:
            raise WorkflowContextError("workflow is not registered") from error
        definition = self._definitions.get(normalized)
        if definition is None:
            raise WorkflowContextError("workflow is not registered")
        try:
            self._security_profiles.assess_workflow(
                name=definition.workflow_id.value,
                version=definition.version,
                owner_module=definition.owner_module,
                risk_level=definition.risk_level,
                network_access=definition.network_access,
                data_classes=definition.data_classes,
                search_enabled=definition.search_enabled,
            )
        except SecurityEvaluationError as error:
            raise WorkflowContextError("workflow is not enabled by its security profile") from error
        return definition

    def validate_context(
        self,
        workflow_id: WorkflowId | str,
        *,
        loaded_skill_count: int,
        uploaded_file_count: int,
        uploaded_image_count: int = 0,
    ) -> WorkflowDefinition:
        definition = self.resolve(workflow_id)
        if (loaded_skill_count and not definition.accepts_skills) or (
            (uploaded_file_count or uploaded_image_count) and not definition.accepts_uploaded_files
        ):
            raise WorkflowContextError("workflow does not accept Skills or uploaded files")
        return definition

    def list_definitions(self) -> tuple[WorkflowDefinition, ...]:
        return tuple(self._definitions.values())


@lru_cache(maxsize=1)
def get_default_workflow_registry() -> WorkflowRegistry:
    """Return the immutable, process-wide registry for production chat routing."""

    return WorkflowRegistry()

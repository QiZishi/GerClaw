"""Dependency wiring for the production Agent Harness composition root."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from agentscope.model import ChatModelBase
from agentscope.skill import Skill as AgentScopeSkill

from gerclaw_api.config import Settings
from gerclaw_api.modules.agent_harness.clinical_state import ClinicalState
from gerclaw_api.modules.agent_harness.components import HarnessComponents
from gerclaw_api.modules.agent_harness.config import ResolvedHarnessConfig
from gerclaw_api.modules.agent_harness.context_snapshot import (
    ProductionContextSnapshotAssembler,
    UploadedInputProjector,
)
from gerclaw_api.modules.agent_harness.planning import (
    AgentFactory,
    DynamicPlan,
    PlanExecutionObserver,
    PlanExecutionSnapshot,
    ProductionAgentFactory,
    TurnClinicalDecision,
    TurnPlanningCoordinator,
)
from gerclaw_api.modules.agent_harness.plugin_runtime import (
    ApprovalCallback,
    CapabilityResult,
    ToolRegistryFactory,
)
from gerclaw_api.modules.agent_harness.plugin_runtime.production import (
    build_production_tool_registry,
)
from gerclaw_api.modules.agent_harness.protocols import (
    AgentContext,
    ConversationHistoryMessage,
)
from gerclaw_api.modules.agent_harness.routing import RouteDecision
from gerclaw_api.modules.agent_harness.run_lifecycle import (
    AttemptRepairObserver,
    ProductionRunLifecycle,
    ReActBoundaryCoordinator,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.directive_runtime import (
    DirectiveApplier,
    DirectiveClaimer,
    DirectiveLoader,
    RuntimeDirectiveCoordinator,
)
from gerclaw_api.modules.agent_harness.safety import detect_high_risk
from gerclaw_api.modules.companion.policy import CompanionWorkflow, is_companion_workflow
from gerclaw_api.modules.contracts import ExecutionContext
from gerclaw_api.modules.document import UploadedDocumentContext
from gerclaw_api.modules.input_output import ImageInput
from gerclaw_api.modules.memory.protocols import MemoryModule
from gerclaw_api.modules.rag.protocols import RAGModule
from gerclaw_api.modules.runtime.budget import RuntimeBudgetExceededError
from gerclaw_api.modules.runtime.models import (
    DataClass,
    ExecutionBudget,
    NetworkAccess,
    RiskLevel,
    RuntimePrincipal,
)
from gerclaw_api.modules.search.protocols import SearchModule
from gerclaw_api.modules.security_evaluation import (
    COMPANION_AGENT_ASSET_NAME,
    CORE_RUNTIME_ASSET_VERSION,
    GERIATRIC_AGENT_ASSET_NAME,
    build_core_runtime_asset_security_registry,
)

CapabilityInvoker = Callable[[str], Awaitable[CapabilityResult]]
CapabilityResultObserver = Callable[
    [PlanExecutionSnapshot, CapabilityResult],
    Awaitable[None],
]


class ProductionHarnessCompositionSetup:
    """Initialize owner protocols and injected component implementations."""

    def __init__(
        self,
        *,
        settings: Settings,
        model: ChatModelBase,
        rag_module: RAGModule,
        memory_module: MemoryModule | None,
        execution: ExecutionContext,
        history: list[ConversationHistoryMessage],
        profile_context: str = "",
        profile_version: int = 0,
        memory_refs: list[str] | None = None,
        session_summary: str = "",
        clinical_state: ClinicalState | None = None,
        search_module: SearchModule | None = None,
        search_enabled: bool = True,
        workflow: CompanionWorkflow = "standard",
        agent_skills: list[AgentScopeSkill] | None = None,
        loaded_skill_ids: list[str] | None = None,
        governed_capability_ids: tuple[str, ...] = (),
        completed_capability_ids: tuple[str, ...] = (),
        capability_results: tuple[CapabilityResult, ...] = (),
        capability_invoker: CapabilityInvoker | None = None,
        capability_result_observer: CapabilityResultObserver | None = None,
        uploaded_documents: list[UploadedDocumentContext] | None = None,
        uploaded_images: list[ImageInput] | None = None,
        runtime_principal: RuntimePrincipal,
        execution_budget: ExecutionBudget | None = None,
        approval_callback: ApprovalCallback | None = None,
        resolved_config: ResolvedHarnessConfig | None = None,
        components: HarnessComponents | None = None,
        tool_registry_factory: ToolRegistryFactory = build_production_tool_registry,
        agent_factory: AgentFactory | None = None,
        route_decision: RouteDecision | None = None,
        dynamic_plan: DynamicPlan | None = None,
        plan_execution_snapshot: PlanExecutionSnapshot | None = None,
        plan_execution_observer: PlanExecutionObserver | None = None,
        clinical_decision: TurnClinicalDecision | None = None,
        preassembled_context: AgentContext | None = None,
        directive_loader: DirectiveLoader | None = None,
        directive_claimer: DirectiveClaimer | None = None,
        directive_applier: DirectiveApplier | None = None,
        attempt_repair_observer: AttemptRepairObserver | None = None,
    ) -> None:
        companion = is_companion_workflow(workflow)
        build_core_runtime_asset_security_registry().assess_agent(
            name=COMPANION_AGENT_ASSET_NAME if companion else GERIATRIC_AGENT_ASSET_NAME,
            version=CORE_RUNTIME_ASSET_VERSION,
            owner_module="agent_harness",
            risk_level=RiskLevel.MEDIUM,
            network_access=NetworkAccess.EXTERNAL,
            data_classes=(
                frozenset({DataClass.INTERNAL})
                if companion
                else frozenset({DataClass.INTERNAL, DataClass.PHI})
            ),
            evidence_backed=not companion,
        )
        self._config = resolved_config or ResolvedHarnessConfig.from_settings(settings)
        self._components = components or HarnessComponents()
        self._route_decision = route_decision
        self._run_lifecycle = self._components.run_lifecycle or ProductionRunLifecycle()
        self._context_assembler = (
            self._components.context_snapshot_assembler or ProductionContextSnapshotAssembler()
        )
        self._tool_registry_factory = tool_registry_factory
        self._model = model
        self._rag_module = rag_module
        self._memory_module = memory_module
        self._execution = execution
        self._history = history
        self._profile_context = profile_context
        self._profile_version = profile_version
        self._memory_refs = memory_refs or []
        self._session_summary = session_summary
        self._clinical_state = clinical_state or ClinicalState()
        self._search_module = search_module
        self._search_enabled = search_enabled
        self._workflow = workflow
        self._agent_skills = agent_skills or []
        self._loaded_skill_ids = loaded_skill_ids or []
        self._governed_capability_ids = governed_capability_ids
        self._completed_capability_ids = completed_capability_ids
        self._capability_results = list(capability_results)
        self._capability_invoker = capability_invoker
        self._capability_result_observer = capability_result_observer
        self._warning_codes: list[str] = []
        self._uploaded_documents = uploaded_documents or []
        self._uploaded_images = uploaded_images or []
        self._uploaded_input = UploadedInputProjector(
            self._uploaded_documents,
            self._uploaded_images,
        )
        self._runtime_principal = runtime_principal
        self._execution_budget = execution_budget or ExecutionBudget(
            max_steps=self._config.max_react_iterations,
            max_output_bytes=self._config.max_output_bytes,
        )
        self._turn_planning = TurnPlanningCoordinator.from_config(
            config=self._config,
            execution_budget=self._execution_budget,
            model_context_tokens=self._model.context_size,
            router=self._components.router,
            planner=self._components.planner,
            route_decision=route_decision,
            dynamic_plan=dynamic_plan,
        )
        self._approval_callback = approval_callback
        self._clinical_decision = clinical_decision
        self._plan_execution_snapshot = plan_execution_snapshot
        self._plan_execution_observer = plan_execution_observer
        self._preassembled_context = preassembled_context
        self._attempt_repair_observer = attempt_repair_observer
        self._runtime_directives = RuntimeDirectiveCoordinator(
            loader=directive_loader,
            claimer=directive_claimer,
            applier=directive_applier,
            preflight=self._turn_planning.check_model,
            error_factory=RuntimeBudgetExceededError,
            risk_classifier=lambda instructions: detect_high_risk("\n".join(instructions)),
            max_per_boundary=self._config.max_directives_per_boundary,
            max_per_run=self._config.max_directives_per_run,
            image_count=len(self._uploaded_images),
        )
        self._react_boundaries = ReActBoundaryCoordinator(
            directives=self._runtime_directives,
            model_preflight=self._turn_planning.check_model,
            tool_preflight=self._turn_planning.check_tool,
            error_factory=RuntimeBudgetExceededError,
            image_count=len(self._uploaded_images),
        )
        self._agent_factory = agent_factory or ProductionAgentFactory(
            model=model,
            config=self._config,
            workflow=workflow,
        )

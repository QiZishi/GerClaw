"""Production composition adapters for existing governed capability owners."""

from agentscope.skill import Skill as AgentScopeSkill
from agentscope.tool import ToolBase, Toolkit
from pydantic import BaseModel

from gerclaw_api.modules.agent_harness.plugin_runtime.contracts import (
    ToolRegistryFactory,
    ToolRegistryPort,
)
from gerclaw_api.modules.runtime.models import (
    ActorRole,
    DataClass,
    NetworkAccess,
    RiskLevel,
    RuntimePrincipal,
    SideEffect,
    ToolCapability,
)
from gerclaw_api.modules.runtime.registry import GovernedToolRegistry
from gerclaw_api.modules.runtime.tool_schemas import (
    SearchKnowledgeInput,
    SearchMemoryInput,
    WebSearchInput,
)
from gerclaw_api.modules.security_evaluation import build_chat_tool_security_registry
from gerclaw_api.modules.skill.agentscope_adapter import SAFE_SKILL_INSTRUCTION_TEMPLATE


def build_production_tool_registry() -> ToolRegistryPort:
    """Construct the existing Runtime-owned registry behind its Harness port."""

    return GovernedToolRegistry(security_profiles=build_chat_tool_security_registry())


def build_chat_toolkit(
    *,
    raw_tools: list[ToolBase],
    principal: RuntimePrincipal,
    skills: list[AgentScopeSkill],
    registry_factory: ToolRegistryFactory,
) -> tuple[
    Toolkit,
    dict[str, ToolCapability],
    dict[str, type[BaseModel]],
]:
    """Register the existing read-only chat tools through the Runtime owner."""

    registry = registry_factory()
    specifications: dict[str, tuple[ToolCapability, type[BaseModel]]] = {
        "search_knowledge": (
            ToolCapability(
                name="search_knowledge",
                version="1.0.0",
                description="Read-only local medical evidence retrieval.",
                required_scopes=frozenset({"rag:read"}),
                allowed_roles=frozenset(
                    {ActorRole.GUEST, ActorRole.PATIENT, ActorRole.DOCTOR}
                ),
                risk_level=RiskLevel.LOW,
                side_effect=SideEffect.NONE,
                network_access=NetworkAccess.INTERNAL,
                data_classes=frozenset({DataClass.INTERNAL}),
            ),
            SearchKnowledgeInput,
        ),
        "search_memory": (
            ToolCapability(
                name="search_memory",
                version="1.0.0",
                description="Read-only retrieval of caller-owned health memory.",
                required_scopes=frozenset({"memory:read"}),
                allowed_roles=frozenset(
                    {ActorRole.GUEST, ActorRole.PATIENT, ActorRole.DOCTOR}
                ),
                risk_level=RiskLevel.LOW,
                side_effect=SideEffect.NONE,
                network_access=NetworkAccess.INTERNAL,
                data_classes=frozenset({DataClass.PHI}),
                patient_scoped=True,
            ),
            SearchMemoryInput,
        ),
        "web_search": (
            ToolCapability(
                name="web_search",
                version="1.0.0",
                description="Read-only redacted external medical evidence search.",
                required_scopes=frozenset({"search:read"}),
                allowed_roles=frozenset(
                    {ActorRole.GUEST, ActorRole.PATIENT, ActorRole.DOCTOR}
                ),
                risk_level=RiskLevel.MEDIUM,
                side_effect=SideEffect.NONE,
                network_access=NetworkAccess.EXTERNAL,
                data_classes=frozenset({DataClass.INTERNAL}),
            ),
            WebSearchInput,
        ),
    }
    for tool in raw_tools:
        specification = specifications.get(tool.name)
        if specification is not None:
            registry.register(tool, *specification)
    tools = list(
        registry.build_tools(
            principal=principal,
            outbound_redacted_tools=frozenset({"web_search"}),
        )
    )
    toolkit = Toolkit(
        tools=tools,
        skills_or_loaders=skills,
        skill_instruction_template=SAFE_SKILL_INSTRUCTION_TEMPLATE,
    )
    return (
        toolkit,
        {capability.name: capability for capability in registry.capabilities()},
        registry.input_models(),
    )

"""Security-risk profile gate tests for the production Runtime toolkit."""

from __future__ import annotations

import pytest
from agentscope.tool import FunctionTool
from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.modules.runtime import (
    DataClass,
    GovernedToolRegistry,
    NetworkAccess,
    RiskLevel,
    SideEffect,
    ToolCapability,
)
from gerclaw_api.modules.runtime.models import ActorRole, RuntimePrincipal
from gerclaw_api.modules.runtime.registry import ToolSecurityProfileError
from gerclaw_api.modules.security_evaluation import (
    SecurityAssetKind,
    SecurityControl,
    SecurityEvaluationError,
    SecurityRiskProfile,
    SecurityThreat,
    build_chat_tool_security_registry,
)


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=100)


def capability(
    name: str,
    *,
    risk_level: RiskLevel,
    network_access: NetworkAccess,
    data_classes: frozenset[DataClass],
    patient_scoped: bool = False,
) -> ToolCapability:
    return ToolCapability(
        name=name,
        version="1.0.0",
        description="Bounded read-only search used by a Runtime security test.",
        required_scopes=frozenset({"search:read"}),
        allowed_roles=frozenset({ActorRole.GUEST}),
        risk_level=risk_level,
        side_effect=SideEffect.NONE,
        network_access=network_access,
        data_classes=data_classes,
        patient_scoped=patient_scoped,
    )


def test_production_profiles_bind_exact_capability_and_controls() -> None:
    profiles = build_chat_tool_security_registry()
    verdict = profiles.assess_tool(
        capability(
            "search_knowledge",
            risk_level=RiskLevel.LOW,
            network_access=NetworkAccess.INTERNAL,
            data_classes=frozenset({DataClass.INTERNAL}),
        )
    )

    assert verdict.allowed is True
    assert verdict.profile_id == "security.tool.search_knowledge"

    with pytest.raises(SecurityEvaluationError, match="risk level differs"):
        profiles.assess_tool(
            capability(
                "search_knowledge",
                risk_level=RiskLevel.MEDIUM,
                network_access=NetworkAccess.INTERNAL,
                data_classes=frozenset({DataClass.INTERNAL}),
            )
        )

    with pytest.raises(SecurityEvaluationError, match="patient-ownership"):
        profiles.assess_tool(
            capability(
                "search_knowledge",
                risk_level=RiskLevel.LOW,
                network_access=NetworkAccess.INTERNAL,
                data_classes=frozenset({DataClass.INTERNAL}),
                patient_scoped=True,
            )
        )


def test_profile_with_missing_required_runtime_control_fails_closed() -> None:
    profile = SecurityRiskProfile(
        profile_id="security.tool.search_knowledge",
        profile_version="1.0.0",
        asset_kind=SecurityAssetKind.TOOL,
        asset_name="search_knowledge",
        asset_version="1.0.0",
        owner_module="rag",
        risk_level=RiskLevel.LOW,
        network_access=NetworkAccess.INTERNAL,
        data_classes=frozenset({DataClass.INTERNAL}),
        threats=frozenset({SecurityThreat.RAG_POISONING}),
        required_controls=frozenset({SecurityControl.INPUT_SCHEMA}),
        residual_risk="A deliberately incomplete test-only security profile.",
    )
    profiles = build_chat_tool_security_registry()
    profiles = type(profiles)((profile,))
    with pytest.raises(SecurityEvaluationError, match="omits a mandatory Runtime control"):
        profiles.assess_tool(
            capability(
                "search_knowledge",
                risk_level=RiskLevel.LOW,
                network_access=NetworkAccess.INTERNAL,
                data_classes=frozenset({DataClass.INTERNAL}),
            )
        )


def test_runtime_registry_rejects_unprofiled_and_unredacted_external_tools() -> None:
    async def search(query: str) -> str:
        return query

    unprofiled = GovernedToolRegistry(security_profiles=build_chat_tool_security_registry())
    unknown_delegate = FunctionTool(
        search,
        name="unknown_tool",
        description="A test tool that cannot be enabled without a risk profile.",
        is_read_only=True,
    )
    with pytest.raises(ToolSecurityProfileError, match="no server-owned security risk profile"):
        unprofiled.register(
            unknown_delegate,
            capability(
                "unknown_tool",
                risk_level=RiskLevel.LOW,
                network_access=NetworkAccess.NONE,
                data_classes=frozenset({DataClass.INTERNAL}),
            ),
            SearchInput,
        )

    registry = GovernedToolRegistry(security_profiles=build_chat_tool_security_registry())
    delegate = FunctionTool(
        search,
        name="web_search",
        description="A bounded external query for Runtime profile testing.",
        is_read_only=True,
    )
    registry.register(
        delegate,
        capability(
            "web_search",
            risk_level=RiskLevel.MEDIUM,
            network_access=NetworkAccess.EXTERNAL,
            data_classes=frozenset({DataClass.INTERNAL}),
        ),
        SearchInput,
    )
    principal = RuntimePrincipal(
        tenant_id="tenant_abcdefgh",
        actor_id="actor_abcdefgh",
        role=ActorRole.GUEST,
        scopes=frozenset({"search:read"}),
    )
    with pytest.raises(ToolSecurityProfileError, match="without redaction proof"):
        registry.build_tools(principal=principal)
    assert (
        len(
            registry.build_tools(
                principal=principal,
                outbound_redacted_tools=frozenset({"web_search"}),
            )
        )
        == 1
    )

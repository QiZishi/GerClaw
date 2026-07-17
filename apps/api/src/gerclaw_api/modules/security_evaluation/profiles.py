"""Reviewed profiles for the only tools enabled by the production chat Harness."""

from __future__ import annotations

from gerclaw_api.modules.runtime.models import DataClass, NetworkAccess, RiskLevel
from gerclaw_api.modules.security_evaluation.evaluator import SecurityProfileRegistry
from gerclaw_api.modules.security_evaluation.models import (
    SecurityAssetKind,
    SecurityControl,
    SecurityRiskProfile,
    SecurityThreat,
)

_BASE_CONTROLS = frozenset(
    {
        SecurityControl.INPUT_SCHEMA,
        SecurityControl.OUTPUT_BOUNDARY,
        SecurityControl.RUNTIME_PERMISSION,
        SecurityControl.TIMEOUT,
        SecurityControl.EXECUTION_BUDGET,
        SecurityControl.UNTRUSTED_DATA_ISOLATION,
    }
)

CHAT_TOOL_SECURITY_PROFILES: tuple[SecurityRiskProfile, ...] = (
    SecurityRiskProfile(
        profile_id="security.tool.search_knowledge",
        profile_version="1.0.0",
        asset_kind=SecurityAssetKind.TOOL,
        asset_name="search_knowledge",
        asset_version="1.0.0",
        owner_module="rag",
        risk_level=RiskLevel.LOW,
        network_access=NetworkAccess.INTERNAL,
        data_classes=frozenset({DataClass.INTERNAL}),
        threats=frozenset(
            {
                SecurityThreat.INDIRECT_PROMPT_INJECTION,
                SecurityThreat.RAG_POISONING,
                SecurityThreat.HALLUCINATED_EVIDENCE,
                SecurityThreat.RESOURCE_EXHAUSTION,
            }
        ),
        required_controls=_BASE_CONTROLS | frozenset({SecurityControl.EVIDENCE_PROVENANCE}),
        residual_risk="Retrieved text remains untrusted and may be incomplete or outdated.",
    ),
    SecurityRiskProfile(
        profile_id="security.tool.search_memory",
        profile_version="1.0.0",
        asset_kind=SecurityAssetKind.TOOL,
        asset_name="search_memory",
        asset_version="1.0.0",
        owner_module="memory",
        risk_level=RiskLevel.LOW,
        network_access=NetworkAccess.INTERNAL,
        data_classes=frozenset({DataClass.PHI}),
        threats=frozenset(
            {
                SecurityThreat.MEMORY_POISONING,
                SecurityThreat.CROSS_PATIENT_ACCESS,
                SecurityThreat.INDIRECT_PROMPT_INJECTION,
                SecurityThreat.RESOURCE_EXHAUSTION,
            }
        ),
        required_controls=_BASE_CONTROLS | frozenset({SecurityControl.PATIENT_OWNERSHIP}),
        residual_risk=(
            "Retrieved self-reported facts remain provisional and require clinical verification."
        ),
    ),
    SecurityRiskProfile(
        profile_id="security.tool.web_search",
        profile_version="1.0.0",
        asset_kind=SecurityAssetKind.TOOL,
        asset_name="web_search",
        asset_version="1.0.0",
        owner_module="search",
        risk_level=RiskLevel.MEDIUM,
        network_access=NetworkAccess.EXTERNAL,
        data_classes=frozenset({DataClass.INTERNAL}),
        threats=frozenset(
            {
                SecurityThreat.INDIRECT_PROMPT_INJECTION,
                SecurityThreat.RAG_POISONING,
                SecurityThreat.SENSITIVE_EGRESS,
                SecurityThreat.HALLUCINATED_EVIDENCE,
                SecurityThreat.RESOURCE_EXHAUSTION,
            }
        ),
        required_controls=_BASE_CONTROLS
        | frozenset(
            {
                SecurityControl.EVIDENCE_PROVENANCE,
                SecurityControl.EXTERNAL_EGRESS_REDACTION,
            }
        ),
        residual_risk=(
            "External sources can be unavailable, untrusted, or unsuitable as primary evidence."
        ),
    ),
)


def build_chat_tool_security_registry() -> SecurityProfileRegistry:
    """Return a request-local immutable-profile evaluator for the chat toolkit."""

    return SecurityProfileRegistry(CHAT_TOOL_SECURITY_PROFILES)

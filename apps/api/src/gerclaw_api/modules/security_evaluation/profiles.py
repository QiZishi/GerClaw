"""Reviewed profiles for the production Chat Runtime assets."""

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

_BASE_RUNTIME_ASSET_CONTROLS = frozenset(
    {
        SecurityControl.INPUT_SCHEMA,
        SecurityControl.OUTPUT_BOUNDARY,
        SecurityControl.EXECUTION_BUDGET,
        SecurityControl.UNTRUSTED_DATA_ISOLATION,
    }
)

GERIATRIC_AGENT_ASSET_NAME = "gerclaw_geriatric_specialist"
COMPANION_AGENT_ASSET_NAME = "gerclaw_emotional_companion"
MEMORY_ASSET_NAME = "health_memory"
LOCAL_MEDICAL_CORPUS_ASSET_NAME = "local_medical_corpus"
CORE_RUNTIME_ASSET_VERSION = "1.0.0"

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

CORE_RUNTIME_ASSET_SECURITY_PROFILES: tuple[SecurityRiskProfile, ...] = (
    SecurityRiskProfile(
        profile_id="security.agent.gerclaw_geriatric_specialist",
        profile_version="1.0.0",
        asset_kind=SecurityAssetKind.AGENT,
        asset_name=GERIATRIC_AGENT_ASSET_NAME,
        asset_version=CORE_RUNTIME_ASSET_VERSION,
        owner_module="agent_harness",
        risk_level=RiskLevel.MEDIUM,
        network_access=NetworkAccess.EXTERNAL,
        data_classes=frozenset({DataClass.INTERNAL, DataClass.PHI}),
        threats=frozenset(
            {
                SecurityThreat.INDIRECT_PROMPT_INJECTION,
                SecurityThreat.RAG_POISONING,
                SecurityThreat.MEMORY_POISONING,
                SecurityThreat.CROSS_PATIENT_ACCESS,
                SecurityThreat.SENSITIVE_EGRESS,
                SecurityThreat.HALLUCINATED_EVIDENCE,
                SecurityThreat.MEDICAL_HARM,
                SecurityThreat.RESOURCE_EXHAUSTION,
            }
        ),
        required_controls=_BASE_RUNTIME_ASSET_CONTROLS
        | frozenset(
            {
                SecurityControl.PATIENT_OWNERSHIP,
                SecurityControl.EXTERNAL_EGRESS_REDACTION,
                SecurityControl.EVIDENCE_PROVENANCE,
            }
        ),
        residual_risk=(
            "Evidence-backed medical assistance remains advisory and may require clinician review."
        ),
    ),
    SecurityRiskProfile(
        profile_id="security.agent.gerclaw_emotional_companion",
        profile_version="1.0.0",
        asset_kind=SecurityAssetKind.AGENT,
        asset_name=COMPANION_AGENT_ASSET_NAME,
        asset_version=CORE_RUNTIME_ASSET_VERSION,
        owner_module="agent_harness",
        risk_level=RiskLevel.MEDIUM,
        network_access=NetworkAccess.EXTERNAL,
        data_classes=frozenset({DataClass.INTERNAL}),
        threats=frozenset(
            {
                SecurityThreat.INDIRECT_PROMPT_INJECTION,
                SecurityThreat.SENSITIVE_EGRESS,
                SecurityThreat.MEDICAL_HARM,
                SecurityThreat.RESOURCE_EXHAUSTION,
            }
        ),
        required_controls=_BASE_RUNTIME_ASSET_CONTROLS
        | frozenset({SecurityControl.EXTERNAL_EGRESS_REDACTION}),
        residual_risk=(
            "Supportive responses may be insufficient; emergencies remain "
            "deterministically escalated."
        ),
    ),
    SecurityRiskProfile(
        profile_id="security.memory.health_memory",
        profile_version="1.0.0",
        asset_kind=SecurityAssetKind.MEMORY,
        asset_name=MEMORY_ASSET_NAME,
        asset_version=CORE_RUNTIME_ASSET_VERSION,
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
        required_controls=_BASE_RUNTIME_ASSET_CONTROLS
        | frozenset({SecurityControl.PATIENT_OWNERSHIP}),
        residual_risk=(
            "Self-reported health facts remain provisional and cannot replace current evidence."
        ),
    ),
    SecurityRiskProfile(
        profile_id="security.rag_source.local_medical_corpus",
        profile_version="1.0.0",
        asset_kind=SecurityAssetKind.RAG_SOURCE,
        asset_name=LOCAL_MEDICAL_CORPUS_ASSET_NAME,
        asset_version=CORE_RUNTIME_ASSET_VERSION,
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
        required_controls=_BASE_RUNTIME_ASSET_CONTROLS
        | frozenset({SecurityControl.EVIDENCE_PROVENANCE}),
        residual_risk=(
            "Local corpus material may be incomplete, outdated, or unsuitable for a specific case."
        ),
    ),
)


def build_chat_tool_security_registry() -> SecurityProfileRegistry:
    """Return a request-local immutable-profile evaluator for the chat toolkit."""

    return SecurityProfileRegistry(CHAT_TOOL_SECURITY_PROFILES)


def build_core_runtime_asset_security_registry() -> SecurityProfileRegistry:
    """Return immutable profiles for the Agent, Memory, and local RAG assets."""

    return SecurityProfileRegistry(CORE_RUNTIME_ASSET_SECURITY_PROFILES)

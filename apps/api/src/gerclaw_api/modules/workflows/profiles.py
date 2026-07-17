"""Reviewed risk profiles for each workflow enabled by the Runtime Harness."""

from __future__ import annotations

from gerclaw_api.modules.runtime.models import DataClass, NetworkAccess, RiskLevel
from gerclaw_api.modules.security_evaluation import (
    SecurityAssetKind,
    SecurityControl,
    SecurityProfileRegistry,
    SecurityRiskProfile,
    SecurityThreat,
)

_BASE_CONTROLS = frozenset(
    {
        SecurityControl.INPUT_SCHEMA,
        SecurityControl.OUTPUT_BOUNDARY,
        SecurityControl.EXECUTION_BUDGET,
        SecurityControl.UNTRUSTED_DATA_ISOLATION,
    }
)

WORKFLOW_SECURITY_PROFILES: tuple[SecurityRiskProfile, ...] = (
    SecurityRiskProfile(
        profile_id="security.workflow.standard",
        profile_version="1.0.0",
        asset_kind=SecurityAssetKind.WORKFLOW,
        asset_name="standard",
        asset_version="1.0.0",
        owner_module="agent_harness",
        risk_level=RiskLevel.MEDIUM,
        network_access=NetworkAccess.EXTERNAL,
        data_classes=frozenset({DataClass.INTERNAL, DataClass.PHI}),
        threats=frozenset(
            {
                SecurityThreat.INDIRECT_PROMPT_INJECTION,
                SecurityThreat.RAG_POISONING,
                SecurityThreat.MEMORY_POISONING,
                SecurityThreat.SENSITIVE_EGRESS,
                SecurityThreat.HALLUCINATED_EVIDENCE,
                SecurityThreat.RESOURCE_EXHAUSTION,
            }
        ),
        required_controls=_BASE_CONTROLS
        | frozenset(
            {
                SecurityControl.PATIENT_OWNERSHIP,
                SecurityControl.EVIDENCE_PROVENANCE,
                SecurityControl.EXTERNAL_EGRESS_REDACTION,
            }
        ),
        residual_risk="Model and external evidence remain fallible; medical output stays advisory.",
    ),
    SecurityRiskProfile(
        profile_id="security.workflow.cga",
        profile_version="1.0.0",
        asset_kind=SecurityAssetKind.WORKFLOW,
        asset_name="cga",
        asset_version="1.0.0",
        owner_module="cga",
        risk_level=RiskLevel.MEDIUM,
        network_access=NetworkAccess.INTERNAL,
        data_classes=frozenset({DataClass.INTERNAL, DataClass.PHI}),
        threats=frozenset(
            {
                SecurityThreat.INDIRECT_PROMPT_INJECTION,
                SecurityThreat.MEMORY_POISONING,
                SecurityThreat.CROSS_PATIENT_ACCESS,
                SecurityThreat.RESOURCE_EXHAUSTION,
            }
        ),
        required_controls=_BASE_CONTROLS | frozenset({SecurityControl.PATIENT_OWNERSHIP}),
        residual_risk=(
            "Conversation assistance cannot replace deterministic scoring or clinician review."
        ),
    ),
    SecurityRiskProfile(
        profile_id="security.workflow.companion",
        profile_version="1.0.0",
        asset_kind=SecurityAssetKind.WORKFLOW,
        asset_name="companion",
        asset_version="1.0.0",
        owner_module="companion",
        risk_level=RiskLevel.MEDIUM,
        network_access=NetworkAccess.NONE,
        data_classes=frozenset({DataClass.INTERNAL}),
        threats=frozenset(
            {
                SecurityThreat.INDIRECT_PROMPT_INJECTION,
                SecurityThreat.RESOURCE_EXHAUSTION,
            }
        ),
        required_controls=_BASE_CONTROLS,
        residual_risk=(
            "Supportive language may be insufficient; emergencies remain "
            "deterministically escalated."
        ),
    ),
    SecurityRiskProfile(
        profile_id="security.workflow.prescription",
        profile_version="1.0.0",
        asset_kind=SecurityAssetKind.WORKFLOW,
        asset_name="prescription",
        asset_version="1.0.0",
        owner_module="prescription",
        risk_level=RiskLevel.HIGH,
        network_access=NetworkAccess.EXTERNAL,
        data_classes=frozenset({DataClass.INTERNAL, DataClass.PHI}),
        threats=frozenset(
            {
                SecurityThreat.INDIRECT_PROMPT_INJECTION,
                SecurityThreat.RAG_POISONING,
                SecurityThreat.SENSITIVE_EGRESS,
                SecurityThreat.HALLUCINATED_EVIDENCE,
                SecurityThreat.RESOURCE_EXHAUSTION,
                SecurityThreat.MEDICAL_HARM,
            }
        ),
        required_controls=_BASE_CONTROLS
        | frozenset(
            {
                SecurityControl.PATIENT_OWNERSHIP,
                SecurityControl.EVIDENCE_PROVENANCE,
                SecurityControl.EXTERNAL_EGRESS_REDACTION,
            }
        ),
        residual_risk=(
            "A draft may still be clinically unsuitable; it remains evidence-bound, "
            "review-only and cannot become an executable prescription."
        ),
    ),
)


def build_workflow_security_registry() -> SecurityProfileRegistry:
    return SecurityProfileRegistry(WORKFLOW_SECURITY_PROFILES)

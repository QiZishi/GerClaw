"""Fail-closed security-profile gate used while Runtime tools are registered."""

from __future__ import annotations

from collections.abc import Iterable

from gerclaw_api.modules.runtime.models import (
    DataClass,
    NetworkAccess,
    RiskLevel,
    ToolCapability,
)
from gerclaw_api.modules.security_evaluation.models import (
    SecurityAssetKind,
    SecurityControl,
    SecurityEvaluationVerdict,
    SecurityProfileStatus,
    SecurityRiskProfile,
)

_BASE_TOOL_CONTROLS = frozenset(
    {
        SecurityControl.INPUT_SCHEMA,
        SecurityControl.OUTPUT_BOUNDARY,
        SecurityControl.RUNTIME_PERMISSION,
        SecurityControl.TIMEOUT,
        SecurityControl.EXECUTION_BUDGET,
    }
)

_BASE_WORKFLOW_CONTROLS = frozenset(
    {
        SecurityControl.INPUT_SCHEMA,
        SecurityControl.OUTPUT_BOUNDARY,
        SecurityControl.EXECUTION_BUDGET,
        SecurityControl.UNTRUSTED_DATA_ISOLATION,
    }
)


class SecurityEvaluationError(ValueError):
    """A Runtime asset has no compatible, active reviewed profile."""


class SecurityProfileRegistry:
    """Server-owned profiles keyed by the exact enabled asset and version."""

    def __init__(self, profiles: Iterable[SecurityRiskProfile] = ()) -> None:
        self._profiles: dict[tuple[SecurityAssetKind, str], SecurityRiskProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: SecurityRiskProfile) -> None:
        key = (profile.asset_kind, profile.asset_name)
        if key in self._profiles:
            raise SecurityEvaluationError(
                f"duplicate security profile for {profile.asset_kind}:{profile.asset_name}"
            )
        self._profiles[key] = profile

    def profile_for(self, kind: SecurityAssetKind, name: str) -> SecurityRiskProfile | None:
        return self._profiles.get((kind, name))

    def assess_asset(
        self,
        *,
        asset_kind: SecurityAssetKind,
        asset_name: str,
        asset_version: str,
        owner_module: str,
        risk_level: RiskLevel,
        network_access: NetworkAccess,
        data_classes: frozenset[DataClass],
    ) -> SecurityEvaluationVerdict:
        """Verify a server-owned asset before it can be enabled by Runtime."""

        profile = self.profile_for(asset_kind, asset_name)
        if profile is None:
            raise SecurityEvaluationError(
                f"{asset_kind.value} {asset_name} has no server-owned security risk profile"
            )
        if profile.status is not SecurityProfileStatus.ACTIVE:
            raise SecurityEvaluationError(
                f"{asset_kind.value} {asset_name} security profile is blocked"
            )
        if profile.asset_version != asset_version:
            raise SecurityEvaluationError(
                f"{asset_kind.value} {asset_name} version is not bound to its security profile"
            )
        if profile.owner_module != owner_module:
            raise SecurityEvaluationError(
                f"{asset_kind.value} {asset_name} owner differs from its security profile"
            )
        if profile.risk_level is not risk_level:
            raise SecurityEvaluationError(
                f"{asset_kind.value} {asset_name} risk level differs from its security profile"
            )
        if profile.network_access is not network_access:
            raise SecurityEvaluationError(
                f"{asset_kind.value} {asset_name} network access differs from its security profile"
            )
        if not data_classes.issubset(profile.data_classes):
            raise SecurityEvaluationError(
                f"{asset_kind.value} {asset_name} data classes exceed its security profile"
            )
        return SecurityEvaluationVerdict(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            asset_kind=asset_kind,
            asset_name=asset_name,
            asset_version=asset_version,
        )

    def assess_tool(
        self,
        capability: ToolCapability,
        *,
        outbound_data_redacted: bool | None = None,
    ) -> SecurityEvaluationVerdict:
        """Reject an unprofiled or broadened tool before it can reach an Agent."""

        profile = self.profile_for(SecurityAssetKind.TOOL, capability.name)
        if profile is None:
            raise SecurityEvaluationError(
                f"tool {capability.name} has no server-owned security risk profile"
            )
        verdict = self.assess_asset(
            asset_kind=SecurityAssetKind.TOOL,
            asset_name=capability.name,
            asset_version=capability.version,
            owner_module=profile.owner_module,
            risk_level=capability.risk_level,
            network_access=capability.network_access,
            data_classes=capability.data_classes,
        )
        if not _BASE_TOOL_CONTROLS.issubset(profile.required_controls):
            raise SecurityEvaluationError(
                f"tool {capability.name} profile omits a mandatory Runtime control"
            )
        if (
            capability.patient_scoped
            and SecurityControl.PATIENT_OWNERSHIP not in profile.required_controls
        ):
            raise SecurityEvaluationError(
                f"patient-scoped tool {capability.name} omits patient-ownership control"
            )
        if capability.network_access is NetworkAccess.EXTERNAL:
            if SecurityControl.EXTERNAL_EGRESS_REDACTION not in profile.required_controls:
                raise SecurityEvaluationError(
                    f"external tool {capability.name} omits egress-redaction control"
                )
            if outbound_data_redacted is False:
                raise SecurityEvaluationError(
                    f"external tool {capability.name} was built without redaction proof"
                )
        return verdict

    def assess_workflow(
        self,
        *,
        name: str,
        version: str,
        owner_module: str,
        risk_level: RiskLevel,
        network_access: NetworkAccess,
        data_classes: frozenset[DataClass],
        search_enabled: bool,
    ) -> SecurityEvaluationVerdict:
        """Reject a workflow whose active profile omits its executable controls.

        Asset-field matching alone is insufficient: a profile with the correct
        name and version but no input, output, budget, provenance, ownership,
        or egress controls would otherwise enable a real workflow.
        """

        profile = self.profile_for(SecurityAssetKind.WORKFLOW, name)
        if profile is None:
            raise SecurityEvaluationError(
                f"workflow {name} has no server-owned security risk profile"
            )
        verdict = self.assess_asset(
            asset_kind=SecurityAssetKind.WORKFLOW,
            asset_name=name,
            asset_version=version,
            owner_module=owner_module,
            risk_level=risk_level,
            network_access=network_access,
            data_classes=data_classes,
        )
        if not _BASE_WORKFLOW_CONTROLS.issubset(profile.required_controls):
            raise SecurityEvaluationError(
                f"workflow {name} profile omits a mandatory Runtime control"
            )
        if (
            DataClass.PHI in data_classes
            and SecurityControl.PATIENT_OWNERSHIP not in profile.required_controls
        ):
            raise SecurityEvaluationError(f"PHI workflow {name} omits patient-ownership control")
        if (
            network_access is NetworkAccess.EXTERNAL
            and SecurityControl.EXTERNAL_EGRESS_REDACTION not in profile.required_controls
        ):
            raise SecurityEvaluationError(
                f"external workflow {name} omits egress-redaction control"
            )
        if search_enabled and SecurityControl.EVIDENCE_PROVENANCE not in profile.required_controls:
            raise SecurityEvaluationError(
                f"search-enabled workflow {name} omits evidence-provenance control"
            )
        return verdict

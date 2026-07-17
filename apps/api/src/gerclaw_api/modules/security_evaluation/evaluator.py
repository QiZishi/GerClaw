"""Fail-closed security-profile gate used while Runtime tools are registered."""

from __future__ import annotations

from collections.abc import Iterable

from gerclaw_api.modules.runtime.models import NetworkAccess, ToolCapability
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
        if profile.status is not SecurityProfileStatus.ACTIVE:
            raise SecurityEvaluationError(f"tool {capability.name} security profile is blocked")
        if profile.asset_version != capability.version:
            raise SecurityEvaluationError(
                f"tool {capability.name} version is not bound to its security profile"
            )
        if profile.risk_level is not capability.risk_level:
            raise SecurityEvaluationError(
                f"tool {capability.name} risk level differs from its security profile"
            )
        if profile.network_access is not capability.network_access:
            raise SecurityEvaluationError(
                f"tool {capability.name} network access differs from its security profile"
            )
        if not capability.data_classes.issubset(profile.data_classes):
            raise SecurityEvaluationError(
                f"tool {capability.name} data classes exceed its security profile"
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
        return SecurityEvaluationVerdict(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            asset_kind=SecurityAssetKind.TOOL,
            asset_name=capability.name,
            asset_version=capability.version,
        )

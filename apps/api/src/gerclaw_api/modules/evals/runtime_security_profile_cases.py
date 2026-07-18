"""Reviewed content-free cases for core Runtime security-profile admission."""

from __future__ import annotations

from gerclaw_api.modules.evals.models import RuntimeSecurityProfileEvalCase
from gerclaw_api.modules.security_evaluation import (
    COMPANION_AGENT_ASSET_NAME,
    GERIATRIC_AGENT_ASSET_NAME,
    LOCAL_MEDICAL_CORPUS_ASSET_NAME,
    MEMORY_ASSET_NAME,
    SecurityAssetKind,
)

_CORE_ASSETS: tuple[tuple[SecurityAssetKind, str], ...] = (
    (SecurityAssetKind.AGENT, GERIATRIC_AGENT_ASSET_NAME),
    (SecurityAssetKind.AGENT, COMPANION_AGENT_ASSET_NAME),
    (SecurityAssetKind.MEMORY, MEMORY_ASSET_NAME),
    (SecurityAssetKind.RAG_SOURCE, LOCAL_MEDICAL_CORPUS_ASSET_NAME),
)

RUNTIME_SECURITY_PROFILE_GOLDEN_CASES: tuple[RuntimeSecurityProfileEvalCase, ...] = (
    tuple(
        RuntimeSecurityProfileEvalCase(
            case_id=f"runtime-security-profile.{asset_kind.value}.{asset_name}.admit",
            title=f"{asset_name} 的已审核 Runtime 档案可准入",
            asset_kind=asset_kind,
            asset_name=asset_name,
            expected_allowed=True,
        )
        for asset_kind, asset_name in _CORE_ASSETS
    )
    + tuple(
        RuntimeSecurityProfileEvalCase(
            case_id=f"runtime-security-profile.{asset_kind.value}.{asset_name}.version_mismatch",
            title=f"{asset_name} 的版本漂移必须被拒绝",
            asset_kind=asset_kind,
            asset_name=asset_name,
            mutation="version_mismatch",
            expected_allowed=False,
        )
        for asset_kind, asset_name in _CORE_ASSETS
    )
    + tuple(
        RuntimeSecurityProfileEvalCase(
            case_id=(
                f"runtime-security-profile.{asset_kind.value}.{asset_name}.missing_execution_budget"
            ),
            title=f"{asset_name} 缺少执行预算控制必须被拒绝",
            asset_kind=asset_kind,
            asset_name=asset_name,
            mutation="missing_execution_budget",
            expected_allowed=False,
        )
        for asset_kind, asset_name in _CORE_ASSETS
    )
)

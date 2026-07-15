"""Fail-closed GerClaw policy layered with AgentScope PermissionEngine."""

from __future__ import annotations

from agentscope.permission import PermissionBehavior as AgentScopeBehavior
from agentscope.permission import PermissionDecision as AgentScopeDecision

from gerclaw_api.modules.runtime.models import (
    DataClass,
    NetworkAccess,
    PermissionBehavior,
    PermissionCode,
    PermissionVerdict,
    RiskLevel,
    RuntimePrincipal,
    SideEffect,
    ToolCapability,
    ToolInvocationRequest,
)

POLICY_VERSION = "1.0.0"


class RuntimePermissionEngine:
    """Deterministic authorization whose result cannot be relaxed downstream."""

    def __init__(self, capabilities: list[ToolCapability]) -> None:
        self._capabilities: dict[str, ToolCapability] = {}
        for capability in capabilities:
            if capability.name in self._capabilities:
                raise ValueError(f"duplicate Runtime tool capability: {capability.name}")
            self._capabilities[capability.name] = capability

    def capability(self, name: str) -> ToolCapability | None:
        return self._capabilities.get(name)

    def evaluate(
        self,
        principal: RuntimePrincipal,
        request: ToolInvocationRequest,
        *,
        agentscope_decision: AgentScopeDecision | None = None,
    ) -> PermissionVerdict:
        capability = self._capabilities.get(request.tool_name)
        if capability is None:
            return self._deny(PermissionCode.TOOL_UNKNOWN, "工具未注册。")
        if capability.version != request.tool_version:
            return self._deny(
                PermissionCode.VERSION_MISMATCH,
                "工具版本与已注册 capability 不兼容。",
                capability,
            )
        if not capability.required_scopes.issubset(principal.scopes):
            return self._deny(PermissionCode.SCOPE_REQUIRED, "当前身份缺少所需权限。", capability)
        if principal.role not in capability.allowed_roles:
            return self._deny(PermissionCode.ROLE_FORBIDDEN, "当前角色不能使用该工具。", capability)
        if capability.patient_scoped and not principal.patient_access_verified:
            return self._deny(
                PermissionCode.PATIENT_ACCESS_REQUIRED,
                "尚未验证患者归属或授权。",
                capability,
            )
        if capability.network_access is NetworkAccess.EXTERNAL:
            if DataClass.CREDENTIAL in capability.data_classes:
                return self._deny(
                    PermissionCode.NETWORK_FORBIDDEN,
                    "凭证数据禁止发送到外部工具。",
                    capability,
                )
            sensitive = capability.data_classes.intersection(
                {DataClass.IDENTIFIER, DataClass.PHI, DataClass.HIGH_SENSITIVITY_CLINICAL}
            )
            if sensitive and not request.outbound_data_redacted:
                return self._deny(
                    PermissionCode.PHI_EGRESS_FORBIDDEN,
                    "外部调用尚未通过服务端脱敏证明。",
                    capability,
                )
        if capability.idempotency_required and request.idempotency_key is None:
            return self._deny(
                PermissionCode.APPROVAL_REQUIRED,
                "副作用工具缺少幂等键。",
                capability,
            )
        if capability.risk_level is RiskLevel.CRITICAL:
            return self._deny(
                PermissionCode.CRITICAL_ACTION_DENIED,
                "该动作超过 AI 系统允许的风险等级。",
                capability,
            )
        if agentscope_decision is not None:
            if agentscope_decision.behavior is AgentScopeBehavior.DENY:
                return self._deny(
                    PermissionCode.AGENTSCOPE_DENIED,
                    "AgentScope 工具安全策略拒绝执行。",
                    capability,
                )
            if agentscope_decision.behavior is AgentScopeBehavior.ASK:
                return self._ask(
                    PermissionCode.AGENTSCOPE_APPROVAL_REQUIRED,
                    "AgentScope 工具安全策略要求人工确认。",
                    capability,
                )
            if agentscope_decision.behavior is AgentScopeBehavior.PASSTHROUGH:
                return self._deny(
                    PermissionCode.AGENTSCOPE_DENIED,
                    "AgentScope 未给出可执行授权。",
                    capability,
                )
        if capability.risk_level is RiskLevel.HIGH or capability.side_effect is not SideEffect.NONE:
            if not principal.interactive:
                return self._deny(
                    PermissionCode.APPROVAL_REQUIRED,
                    "当前执行无人值守。不能请求高风险审批。",
                    capability,
                )
            return self._ask(
                PermissionCode.APPROVAL_REQUIRED,
                "该动作需要具备相应角色的人员审批。",
                capability,
            )
        return PermissionVerdict(
            behavior=PermissionBehavior.ALLOW,
            code=PermissionCode.ALLOWED,
            message="工具调用已通过服务端权限检查。",
            policy_version=POLICY_VERSION,
            capability_version=capability.version,
        )

    @staticmethod
    def _deny(
        code: PermissionCode,
        message: str,
        capability: ToolCapability | None = None,
    ) -> PermissionVerdict:
        return PermissionVerdict(
            behavior=PermissionBehavior.DENY,
            code=code,
            message=message,
            policy_version=POLICY_VERSION,
            capability_version=capability.version if capability else None,
        )

    @staticmethod
    def _ask(
        code: PermissionCode,
        message: str,
        capability: ToolCapability,
    ) -> PermissionVerdict:
        return PermissionVerdict(
            behavior=PermissionBehavior.ASK,
            code=code,
            message=message,
            policy_version=POLICY_VERSION,
            capability_version=capability.version,
            approval_roles=tuple(sorted(capability.approval_roles, key=str)),
        )

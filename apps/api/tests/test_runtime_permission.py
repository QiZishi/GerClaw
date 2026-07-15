"""Fail-closed Runtime permission contract tests."""

from __future__ import annotations

import uuid

import pytest
from agentscope.permission import PermissionBehavior as AgentScopeBehavior
from agentscope.permission import PermissionDecision as AgentScopeDecision
from pydantic import ValidationError

from gerclaw_api.modules.runtime import (
    DataClass,
    NetworkAccess,
    PermissionBehavior,
    PermissionCode,
    RiskLevel,
    RuntimePermissionEngine,
    RuntimePrincipal,
    SideEffect,
    ToolCapability,
    ToolInvocationRequest,
)
from gerclaw_api.modules.runtime.models import ActorRole


def capability(**overrides: object) -> ToolCapability:
    values: dict[str, object] = {
        "name": "search_knowledge",
        "version": "1.0.0",
        "description": "Read-only local medical evidence search.",
        "required_scopes": frozenset({"rag:read"}),
        "allowed_roles": frozenset({ActorRole.GUEST, ActorRole.PATIENT, ActorRole.DOCTOR}),
        "risk_level": RiskLevel.LOW,
        "side_effect": SideEffect.NONE,
        "network_access": NetworkAccess.INTERNAL,
        "data_classes": frozenset({DataClass.INTERNAL}),
    }
    values.update(overrides)
    return ToolCapability.model_validate(values)


def principal(**overrides: object) -> RuntimePrincipal:
    values: dict[str, object] = {
        "tenant_id": "tenant_abcdefgh",
        "actor_id": "actor_abcdefgh",
        "role": ActorRole.GUEST,
        "scopes": frozenset({"rag:read"}),
    }
    values.update(overrides)
    return RuntimePrincipal.model_validate(values)


def invocation(**overrides: object) -> ToolInvocationRequest:
    values: dict[str, object] = {
        "invocation_id": "invoke_1234567890abcdef",
        "tool_name": "search_knowledge",
        "tool_version": "1.0.0",
        "arguments": {"query": "跌倒风险"},
    }
    values.update(overrides)
    return ToolInvocationRequest.model_validate(values)


def test_low_risk_registered_read_is_allowed() -> None:
    verdict = RuntimePermissionEngine([capability()]).evaluate(principal(), invocation())
    assert verdict.behavior is PermissionBehavior.ALLOW
    assert verdict.code is PermissionCode.ALLOWED


@pytest.mark.parametrize(
    ("engine", "proposal", "expected"),
    [
        (RuntimePermissionEngine([]), invocation(), PermissionCode.TOOL_UNKNOWN),
        (
            RuntimePermissionEngine([capability()]),
            invocation(tool_version="2.0.0"),
            PermissionCode.VERSION_MISMATCH,
        ),
    ],
)
def test_unknown_and_version_mismatch_fail_closed(
    engine: RuntimePermissionEngine,
    proposal: ToolInvocationRequest,
    expected: PermissionCode,
) -> None:
    verdict = engine.evaluate(principal(), proposal)
    assert verdict.behavior is PermissionBehavior.DENY
    assert verdict.code is expected


def test_scope_role_and_patient_proof_are_all_server_side_boundaries() -> None:
    patient_tool = capability(patient_scoped=True)
    engine = RuntimePermissionEngine([patient_tool])
    assert (
        engine.evaluate(principal(scopes=frozenset()), invocation()).code
        is PermissionCode.SCOPE_REQUIRED
    )
    assert (
        engine.evaluate(principal(role=ActorRole.AUDITOR), invocation()).code
        is PermissionCode.ROLE_FORBIDDEN
    )
    assert (
        engine.evaluate(
            principal(patient_id=uuid.uuid4(), patient_access_verified=False), invocation()
        ).code
        is PermissionCode.PATIENT_ACCESS_REQUIRED
    )


def test_external_phi_requires_server_redaction_proof() -> None:
    external = capability(
        name="web_search",
        required_scopes=frozenset({"search:read"}),
        network_access=NetworkAccess.EXTERNAL,
        data_classes=frozenset({DataClass.PHI}),
    )
    engine = RuntimePermissionEngine([external])
    caller = principal(scopes=frozenset({"search:read"}))
    request = invocation(tool_name="web_search")
    assert engine.evaluate(caller, request).code is PermissionCode.PHI_EGRESS_FORBIDDEN
    assert (
        engine.evaluate(
            caller, request.model_copy(update={"outbound_data_redacted": True})
        ).behavior
        is PermissionBehavior.ALLOW
    )


def test_high_risk_side_effect_asks_only_when_interactive_and_idempotent() -> None:
    high_risk = capability(
        name="clinical_action",
        required_scopes=frozenset({"clinical:write"}),
        allowed_roles=frozenset({ActorRole.DOCTOR}),
        risk_level=RiskLevel.HIGH,
        side_effect=SideEffect.CLINICAL_ACTION,
        idempotency_required=True,
        approval_roles=frozenset({ActorRole.DOCTOR}),
    )
    engine = RuntimePermissionEngine([high_risk])
    caller = principal(role=ActorRole.DOCTOR, scopes=frozenset({"clinical:write"}))
    request = invocation(
        tool_name="clinical_action",
        idempotency_key="idem_1234567890abcdef",
    )
    verdict = engine.evaluate(caller, request)
    assert verdict.behavior is PermissionBehavior.ASK
    assert verdict.approval_roles == (ActorRole.DOCTOR,)
    assert (
        engine.evaluate(caller.model_copy(update={"interactive": False}), request).behavior
        is PermissionBehavior.DENY
    )


def test_critical_action_is_never_approvable() -> None:
    critical = capability(
        name="critical_action",
        risk_level=RiskLevel.CRITICAL,
        side_effect=SideEffect.NONE,
    )
    verdict = RuntimePermissionEngine([critical]).evaluate(
        principal(), invocation(tool_name="critical_action")
    )
    assert verdict.code is PermissionCode.CRITICAL_ACTION_DENIED


def test_agentscope_stricter_decision_cannot_be_relaxed() -> None:
    engine = RuntimePermissionEngine([capability()])
    deny = engine.evaluate(
        principal(),
        invocation(),
        agentscope_decision=AgentScopeDecision(
            behavior=AgentScopeBehavior.DENY,
            message="tool-specific denial",
        ),
    )
    ask = engine.evaluate(
        principal(),
        invocation(),
        agentscope_decision=AgentScopeDecision(
            behavior=AgentScopeBehavior.ASK,
            message="tool-specific approval",
        ),
    )
    assert deny.code is PermissionCode.AGENTSCOPE_DENIED
    assert ask.code is PermissionCode.AGENTSCOPE_APPROVAL_REQUIRED


def test_invalid_capabilities_fail_at_registration_boundary() -> None:
    with pytest.raises(ValidationError):
        capability(side_effect=SideEffect.INTERNAL_WRITE)
    with pytest.raises(ValidationError):
        capability(
            network_access=NetworkAccess.EXTERNAL,
            data_classes=frozenset({DataClass.CREDENTIAL}),
        )
    with pytest.raises(ValueError, match="duplicate Runtime tool capability"):
        RuntimePermissionEngine([capability(), capability()])

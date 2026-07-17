"""Validation tests for shared cross-module DTOs."""

import uuid

import pytest
from pydantic import ValidationError

from gerclaw_api.modules.contracts import (
    AgentRequest,
    AgentResponse,
    Citation,
    ExecutionContext,
    SafetyDecision,
    ToolInvocation,
    ToolResult,
)


def _context() -> ExecutionContext:
    return ExecutionContext(
        request_id="request_contract_001",
        trace_id="trace_contract_001",
        tenant_id="tenant_public0001",
        actor_id="usr_patient_contract0001",
        session_id=uuid.uuid4(),
    )


def _safety() -> SafetyDecision:
    return SafetyDecision(
        reviewed=True,
        disclaimer_applied=True,
        deterministic_diagnosis_blocked=True,
        high_risk_escalation_checked=True,
        notices=["医疗建议不能替代线下医生诊疗。"],
    )


def test_shared_module_contracts_require_evidence_and_safety() -> None:
    request = AgentRequest(context=_context(), text="请帮我评估用药风险")
    response = AgentResponse(
        text="这是辅助风险提示, 不能替代医生诊疗。",
        citations=[
            Citation(
                source_id="local-kb-1",
                title="老年用药原则",
                locator="file.md#section",
                excerpt="证据片段",
                score=0.9,
                corpus="local_knowledge_base",
            )
        ],
        safety=_safety(),
        medical_content=True,
    )
    invocation = ToolInvocation(name="medication.review", arguments={"retry_count": 0})
    tool_result = ToolResult(ok=True, output={"success": True})

    assert request.text.startswith("请帮")
    assert response.citations[0].score == 0.9
    assert invocation.name == "medication.review"
    assert tool_result.ok is True


def test_shared_contracts_reject_unsafe_or_oversized_public_data() -> None:
    with pytest.raises(ValidationError):
        AgentRequest(context=_context(), text="x" * 4_001)
    with pytest.raises(ValidationError, match="deterministic diagnosis"):
        AgentResponse(
            text="您已经确诊患有某疾病。",
            citations=[],
            safety=_safety(),
            medical_content=False,
        )
    with pytest.raises(ValidationError, match="requires at least one"):
        AgentResponse(
            text="这是一条医疗建议。",
            citations=[],
            safety=_safety(),
            medical_content=True,
        )
    clarification = AgentResponse(
        text="目前缺少可核验资料,请补充检查或用药信息。",
        citations=[],
        safety=_safety().model_copy(
            update={
                "notices": [
                    "medical_disclaimer_applied",
                    "evidence_unavailable_clarification",
                ]
            }
        ),
        medical_content=True,
        structured={"evidence_state": "unavailable", "model_invoked": False},
    )
    assert clarification.structured["evidence_state"] == "unavailable"
    with pytest.raises(ValidationError, match="explicit notice"):
        AgentResponse(
            text="目前缺少可核验资料,请补充检查或用药信息。",
            citations=[],
            safety=_safety(),
            medical_content=True,
            structured={"evidence_state": "unavailable", "model_invoked": False},
        )
    with pytest.raises(ValidationError, match="must not use model output"):
        AgentResponse(
            text="目前缺少可核验资料,请补充检查或用药信息。",
            citations=[],
            safety=_safety().model_copy(update={"notices": ["evidence_unavailable_clarification"]}),
            medical_content=True,
            structured={"evidence_state": "unavailable", "model_invoked": True},
        )
    with pytest.raises(ValidationError):
        ToolInvocation(name="INVALID TOOL")


def test_emergency_short_circuit_requires_a_real_escalation() -> None:
    safety = _safety().model_copy(
        update={"notices": ["medical_disclaimer_applied", "high_risk_escalation_applied"]}
    )
    response = AgentResponse(
        text="请立即拨打 120 或前往急诊。内容由 AI 生成,仅供参考。",
        citations=[],
        safety=safety,
        medical_content=True,
        emergency_short_circuit=True,
    )

    assert response.emergency_short_circuit is True

    with pytest.raises(ValidationError, match="requires an applied escalation"):
        AgentResponse(
            text="请立即拨打 120。",
            citations=[],
            safety=_safety(),
            medical_content=True,
            emergency_short_circuit=True,
        )

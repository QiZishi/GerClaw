"""Input/output and tool contracts remain independently replaceable."""

import asyncio
import uuid

import pytest

from gerclaw_api.modules.contracts import (
    AgentRequest,
    AgentResponse,
    Citation,
    ExecutionContext,
    SafetyDecision,
)
from gerclaw_api.modules.input_output.module import (
    InputOutputBoundaryError,
    ProductionInputOutputModule,
)
from gerclaw_api.modules.input_output.protocols import InputOutputModule
from gerclaw_api.modules.tools.protocols import ToolModule


def test_io_and_tool_boundaries_are_independent() -> None:
    assert hasattr(InputOutputModule, "normalize")
    assert hasattr(InputOutputModule, "render")
    assert hasattr(ToolModule, "execute")


def test_production_io_normalizes_text_and_rejects_control_characters() -> None:
    module = ProductionInputOutputModule()
    request = AgentRequest(
        context=ExecutionContext(
            request_id="request_input_output_1",
            trace_id="trace_0123456789abcdef0123456789abcdef",
            tenant_id="tenant_input_output_1",
            actor_id="actor_input_output_1",
            session_id=uuid.uuid4(),
        ),
        text="  检查\r\n文本  ",
    )
    normalized = asyncio.run(module.normalize(request))
    assert normalized.text == "检查\n文本"
    with pytest.raises(InputOutputBoundaryError):
        asyncio.run(module.normalize(request.model_copy(update={"text": "bad\x00text"})))


def test_production_io_projects_only_reviewed_public_fields() -> None:
    module = ProductionInputOutputModule()
    response = AgentResponse(
        text="这是一条有循证来源的辅助健康建议。",
        citations=[
            Citation(
                source_id="source_1",
                title="本地资料",
                locator="chapter 1",
                excerpt="evidence",
                corpus="local_knowledge_base",
            )
        ],
        safety=SafetyDecision(
            reviewed=True,
            disclaimer_applied=True,
            deterministic_diagnosis_blocked=False,
            high_risk_escalation_checked=True,
            notices=["medical_disclaimer_applied"],
        ),
        medical_content=True,
        structured={"internal_model_state": "must not reach SSE"},
    )
    rendered = asyncio.run(module.render(response, "web"))
    assert rendered["text"] == response.text
    assert "structured" not in rendered
    assert rendered["citations"]

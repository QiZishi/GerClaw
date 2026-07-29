"""Shared deterministic answer helper for code-owned clarification turns."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from gerclaw_api.modules.agent_harness.safety import MEDICAL_DISCLAIMER, safety_decision
from gerclaw_api.modules.contracts import AgentResponse
from gerclaw_api.modules.runtime.budget import RuntimeBudgetTracker
from gerclaw_api.security import JsonValue

Emit = Callable[[str, dict[str, JsonValue]], Awaitable[None]]


async def emit_deterministic_clarification(
    *,
    body: str,
    high_risk_codes: list[str],
    emit: Emit,
    budget: RuntimeBudgetTracker,
    structured: dict[str, JsonValue],
    evidence_unavailable: bool = False,
    emergency_short_circuit: bool = False,
    clinical_clarification: bool = False,
) -> AgentResponse:
    text = f"{body}\n\n{MEDICAL_DISCLAIMER}"
    budget.check_wall_clock()
    if emergency_short_circuit:
        await emit(
            "safety_notice",
            {"codes": list(high_risk_codes), "content": body},
        )
    budget.add_output(text)
    await emit("text_delta", {"content": text})
    response = AgentResponse(
        text=text,
        citations=[],
        safety=safety_decision(
            high_risk_codes,
            evidence_unavailable=evidence_unavailable,
            clinical_clarification=clinical_clarification,
        ),
        medical_content=True,
        emergency_short_circuit=emergency_short_circuit,
        structured={
            "model_invoked": False,
            "model_preference": None,
            "model_attempt_count": 0,
            "model_failures": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "tool_names": [],
            "high_risk_codes": list(high_risk_codes),
            "search_attempts": [],
            **structured,
        },
    )
    await emit(
        "done",
        {
            "full_text": response.text,
            "references": [],
            "safety": response.safety.model_dump(mode="json"),
        },
    )
    return response

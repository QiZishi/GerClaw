"""Production normalization and public rendering boundary for Agent I/O."""

from __future__ import annotations

import unicodedata
from typing import Literal

from gerclaw_api.modules.contracts import AgentRequest, AgentResponse
from gerclaw_api.security import JsonValue


class InputOutputBoundaryError(ValueError):
    """Raised when an untrusted channel payload cannot be safely projected."""


def normalize_input_text(text: str) -> str:
    """Return a canonical representation without rejecting user content."""

    return unicodedata.normalize("NFKC", text).replace("\r\n", "\n").strip()


class ProductionInputOutputModule:
    """Canonicalize bounded requests and expose only reviewed public output."""

    async def normalize(self, request: AgentRequest) -> AgentRequest:
        # Re-validate after crossing a module boundary; callers cannot rely on
        # a Python object having originated from Pydantic validation.
        validated = AgentRequest.model_validate(request.model_dump(mode="python"))
        text = normalize_input_text(validated.text)
        attachment_ids = [item.attachment_id for item in validated.attachments]
        if len(attachment_ids) != len(set(attachment_ids)):
            raise InputOutputBoundaryError("duplicate attachment references are not allowed")
        return validated.model_copy(update={"text": text})

    async def render(
        self, response: AgentResponse, channel: Literal["web", "voice"]
    ) -> dict[str, JsonValue]:
        # Never project model metadata, tool state, prompt names or internal
        # accounting through an I/O channel. AgentResponse re-validates the
        # public medical safety and citation invariants here.
        reviewed = AgentResponse.model_validate(response.model_dump(mode="python"))
        if channel == "voice":
            return {
                "text": reviewed.text,
                "safety": reviewed.safety.model_dump(mode="json"),
                "medical_content": reviewed.medical_content,
                "emergency_short_circuit": reviewed.emergency_short_circuit,
            }
        return {
            "text": reviewed.text,
            "citations": [citation.model_dump(mode="json") for citation in reviewed.citations],
            "safety": reviewed.safety.model_dump(mode="json"),
            "medical_content": reviewed.medical_content,
            "emergency_short_circuit": reviewed.emergency_short_circuit,
        }

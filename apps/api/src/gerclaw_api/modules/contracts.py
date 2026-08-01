"""Shared, bounded DTOs used across independently replaceable capability modules."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gerclaw_api.security import JsonValue

STRICT = ConfigDict(extra="forbid")
_EVIDENCE_UNAVAILABLE_NOTICE = "evidence_unavailable_clarification"
_CLINICAL_CLARIFICATION_NOTICE = "clinical_clarification"


class ExecutionContext(BaseModel):
    """Verified identity and correlation data passed to every module."""

    model_config = STRICT

    request_id: str = Field(min_length=8, max_length=64)
    trace_id: str = Field(pattern=r"^trace_[A-Za-z0-9][A-Za-z0-9_.:-]{7,57}$")
    tenant_id: str = Field(min_length=8, max_length=96)
    actor_id: str = Field(min_length=8, max_length=128)
    session_id: uuid.UUID | None = None


class AttachmentRef(BaseModel):
    """Validated reference to previously scanned attachment content."""

    model_config = STRICT

    attachment_id: uuid.UUID
    media_type: Literal["application/pdf", "text/plain", "text/markdown", "image/jpeg", "image/png"]
    size_bytes: int = Field(ge=1, le=25 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class AgentRequest(BaseModel):
    """Normalized request respecting the architecture's 4,000-character boundary."""

    model_config = STRICT

    context: ExecutionContext
    text: str = Field(min_length=1, max_length=4_000)
    attachments: list[AttachmentRef] = Field(default_factory=list, max_length=10)
    channel: Literal["web", "voice"] = "web"


class Citation(BaseModel):
    """Evidence locator with explicit corpus provenance."""

    model_config = STRICT

    source_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=512)
    locator: str = Field(min_length=1, max_length=1_024)
    excerpt: str = Field(min_length=1, max_length=2_000)
    score: float | None = Field(default=None, ge=0)
    corpus: Literal["local_knowledge_base", "web", "uploaded_document", "uploaded_image"]


class SafetyDecision(BaseModel):
    """Mandatory result produced by the Privacy/Safety post-processor."""

    model_config = STRICT

    reviewed: Literal[True]
    disclaimer_applied: bool
    deterministic_diagnosis_blocked: bool
    high_risk_escalation_checked: Literal[True]
    notices: list[str] = Field(min_length=1, max_length=10)


class AgentResponse(BaseModel):
    """Public output that cannot bypass the explicit safety decision contract."""

    model_config = STRICT

    text: str = Field(min_length=1, max_length=50_000)
    citations: list[Citation] = Field(default_factory=list, max_length=50)
    safety: SafetyDecision
    medical_content: bool
    emergency_short_circuit: bool = False
    structured: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_medical_output_invariants(self) -> AgentResponse:
        if self.medical_content and not self.safety.disclaimer_applied:
            raise ValueError("medical content requires an applied disclaimer")
        # Citation coverage is best effort.  The Harness still normalizes
        # unsupported certainty before this DTO is built, but lack of a
        # retrievable source must never discard the complete medical answer.
        # When a source is available, its adoption remains recorded in
        # ``evidence_backed_clinical_conclusion`` and the public citations.
        if self.emergency_short_circuit:
            if not self.medical_content:
                raise ValueError("emergency short circuit must be marked as medical content")
            if self.citations:
                raise ValueError("emergency short circuit must not wait for retrieved evidence")
            if "high_risk_escalation_applied" not in self.safety.notices:
                raise ValueError("emergency short circuit requires an applied escalation")
            if "120" not in self.text and "急诊" not in self.text:
                raise ValueError("emergency short circuit requires an urgent action instruction")
        evidence_unavailable = self.structured.get("evidence_state") == "unavailable"
        if evidence_unavailable:
            if self.citations:
                raise ValueError("evidence-unavailable clarification must not claim citations")
            if _EVIDENCE_UNAVAILABLE_NOTICE not in self.safety.notices:
                raise ValueError("evidence-unavailable clarification requires an explicit notice")
            if self.structured.get("model_invoked") is not False:
                raise ValueError("evidence-unavailable clarification must not use model output")
        clinical_clarification = self.structured.get("response_kind") == "clinical_clarification"
        if clinical_clarification:
            if self.citations:
                raise ValueError("clinical clarification must not claim citations")
            if _CLINICAL_CLARIFICATION_NOTICE not in self.safety.notices:
                raise ValueError("clinical clarification requires an explicit notice")
            if self.structured.get("model_invoked") is not False:
                raise ValueError("clinical clarification must not use model output")
        return self


class ToolInvocation(BaseModel):
    """Validated tool call proposed by the agent harness."""

    model_config = STRICT

    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Auditable tool result without private model reasoning."""

    model_config = STRICT

    ok: bool
    output: dict[str, JsonValue] = Field(default_factory=dict)
    error_code: str | None = Field(default=None, max_length=64)

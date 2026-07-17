"""Fail-closed schemas for the public Chat SSE contract.

SSE ``data`` payloads cross several modules before reaching an untrusted
browser.  Keeping their contract here makes that boundary independently
testable without duplicating the Harness or transport implementation.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from gerclaw_api.modules.contracts import Citation, SafetyDecision
from gerclaw_api.security import JsonValue

if TYPE_CHECKING:
    from gerclaw_api.modules.agent_harness.protocols import StreamEvent

STRICT = ConfigDict(extra="forbid")
PUBLIC_CHAT_SSE_SCHEMA_VERSION = "public-chat-sse-v1"
LOCAL_RAG_EVIDENCE_SCHEMA_VERSION = "local-rag-evidence-v1"


class StreamContractValidationError(ValueError):
    """A bounded, non-sensitive error for a malformed cross-module SSE event."""


class RAGEvidenceContractValidationError(ValueError):
    """A bounded, non-sensitive error for malformed local RAG provenance."""


class ModelOutputContractValidationError(ValueError):
    """A bounded, non-sensitive error for a malformed versioned model output."""


class LocalRAGEvidenceProvenance(BaseModel):
    """Complete provenance required before local RAG may become an AI citation.

    This schema intentionally models metadata only: the RAG module owns result
    content and the agent-safety layer owns public citation projection.  A
    version bump is required when a new provenance field becomes public.
    """

    model_config = STRICT

    document_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    chunk_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    title: str = Field(min_length=1, max_length=512)
    chapter: str = Field(min_length=1, max_length=1_024)
    category: str = Field(min_length=1, max_length=128)
    source_type: Literal["guideline", "consensus", "textbook", "literature"]
    publish_year: int | None = Field(default=None, ge=1900, le=2100)
    chunk_index: int = Field(ge=0, le=1_000_000)
    total_chunks: int = Field(ge=1, le=1_000_000)
    hybrid_score: float | None = Field(default=None, ge=0, le=1_000_000)
    rerank_score: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_chunk_range(self) -> LocalRAGEvidenceProvenance:
        if self.chunk_index >= self.total_chunks:
            raise ValueError("RAG chunk index must be within total chunks")
        return self


class _AgentStartData(BaseModel):
    model_config = STRICT

    agent: Literal["gerclaw_geriatric_specialist", "gerclaw_emotional_companion"]
    status: Literal["running", "replay"]


class _ReasoningSummaryData(BaseModel):
    model_config = STRICT

    content: str = Field(min_length=1, max_length=1_000)
    status: Literal["running"]


class _TextDeltaData(BaseModel):
    model_config = STRICT

    content: str = Field(min_length=1, max_length=50_000)


class _ToolCallData(BaseModel):
    model_config = STRICT

    tool_call_id: str = Field(min_length=1, max_length=256)
    tool_name: str = Field(min_length=1, max_length=128)
    status: Literal["running"]


class _ToolResultData(BaseModel):
    model_config = STRICT

    tool_call_id: str = Field(min_length=1, max_length=256)
    tool_name: str = Field(min_length=1, max_length=128)
    status: Literal["success", "failed", "cancelled"]
    duration_ms: int = Field(ge=0, le=3_600_000)
    result_count: int | None = Field(default=None, ge=0, le=100)
    results: list[dict[str, JsonValue]] | None = Field(default=None, max_length=50)
    skill: str | None = Field(default=None, min_length=1, max_length=100)
    version: str | None = Field(default=None, min_length=1, max_length=100)


class _ApprovalRequiredData(BaseModel):
    model_config = STRICT

    approval_id: uuid.UUID
    tool_name: str = Field(min_length=1, max_length=128)
    status: Literal["pending"]
    expires_at: datetime
    policy_version: str = Field(min_length=1, max_length=100)
    tool_version: str = Field(min_length=1, max_length=100)


class _SafetyNoticeData(BaseModel):
    model_config = STRICT

    codes: list[str] = Field(min_length=1, max_length=10)
    content: str = Field(min_length=1, max_length=1_000)


class _DoneData(BaseModel):
    model_config = STRICT

    full_text: str = Field(min_length=1, max_length=50_000)
    references: list[Citation] = Field(default_factory=list, max_length=50)
    safety: SafetyDecision


class _HarnessDoneData(_DoneData):
    """The Harness terminal payload before Chat Service adds provenance."""


class PublicChatDoneData(_DoneData):
    """Terminal browser payload, versioned by ``PUBLIC_CHAT_SSE_SCHEMA_VERSION``."""

    trace_id: str = Field(pattern=r"^trace_[A-Za-z0-9][A-Za-z0-9_.:-]{7,57}$")
    session_id: uuid.UUID
    replayed: bool = False


_HARNESS_DATA_MODELS: Mapping[str, type[BaseModel]] = {
    "agent_start": _AgentStartData,
    "reasoning_summary": _ReasoningSummaryData,
    "tool_call": _ToolCallData,
    "tool_result": _ToolResultData,
    "approval_required": _ApprovalRequiredData,
    "text_delta": _TextDeltaData,
    "safety_notice": _SafetyNoticeData,
    "done": _HarnessDoneData,
}
_PUBLIC_DATA_MODELS: Mapping[str, type[BaseModel]] = {
    **_HARNESS_DATA_MODELS,
    "done": PublicChatDoneData,
}


def _validate(event: StreamEvent, schemas: Mapping[str, type[BaseModel]]) -> StreamEvent:
    model = schemas.get(event.event_type)
    if model is None:  # defensive: StreamEvent's Literal is the first boundary.
        raise StreamContractValidationError("unsupported public stream event")
    try:
        validated = model.model_validate(event.data)
    except ValidationError as error:
        raise StreamContractValidationError(
            f"invalid {PUBLIC_CHAT_SSE_SCHEMA_VERSION} {event.event_type} payload"
        ) from error
    return event.model_copy(update={"data": validated.model_dump(mode="json")})


def validate_harness_stream_event(event: StreamEvent) -> StreamEvent:
    """Validate a Harness event before callbacks may consume it."""

    return _validate(event, _HARNESS_DATA_MODELS)


def validate_public_chat_stream_event(event: StreamEvent) -> StreamEvent:
    """Validate an event immediately before it enters the browser SSE queue."""

    return _validate(event, _PUBLIC_DATA_MODELS)


def validate_local_rag_evidence_provenance(
    metadata: Mapping[str, JsonValue],
) -> LocalRAGEvidenceProvenance:
    """Validate one local retrieval result before it crosses into an Agent/citation.

    The exception deliberately never includes metadata, content, a query, or a
    provider response.  Callers can safely exclude invalid evidence and enter
    their existing no-evidence path.
    """

    try:
        return LocalRAGEvidenceProvenance.model_validate(metadata)
    except ValidationError as error:
        raise RAGEvidenceContractValidationError(
            f"invalid {LOCAL_RAG_EVIDENCE_SCHEMA_VERSION} provenance"
        ) from error


def validate_versioned_model_output[ModelOutput: BaseModel](
    payload: object,
    *,
    output_model: type[ModelOutput],
    schema_version: str,
) -> ModelOutput:
    """Validate a strict, explicitly versioned structured-model projection.

    The model class owns every domain field.  This shared boundary only makes
    its version an executable contract and guarantees that callers receive a
    bounded error rather than raw provider content.
    """

    try:
        validated = output_model.model_validate(payload)
    except ValidationError as error:
        raise ModelOutputContractValidationError(
            f"invalid {schema_version} model output"
        ) from error
    if getattr(validated, "model_output_schema_version", None) != schema_version:
        raise ModelOutputContractValidationError(f"invalid {schema_version} model output")
    return validated


def validate_versioned_model_output_json[ModelOutput: BaseModel](
    payload: str | bytes | bytearray,
    *,
    output_model: type[ModelOutput],
    schema_version: str,
) -> ModelOutput:
    """JSON counterpart of :func:`validate_versioned_model_output`."""

    try:
        validated = output_model.model_validate_json(payload)
    except ValidationError as error:
        raise ModelOutputContractValidationError(
            f"invalid {schema_version} model output"
        ) from error
    if getattr(validated, "model_output_schema_version", None) != schema_version:
        raise ModelOutputContractValidationError(f"invalid {schema_version} model output")
    return validated

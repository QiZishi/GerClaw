"""Strict chat, session, and SSE contracts for the Agent Harness boundary."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gerclaw_api.modules.contracts import Citation, SafetyDecision

STRICT = ConfigDict(extra="forbid")
SkillId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")]


class ChatRequest(BaseModel):
    """One bounded user turn sent to the production Agent Harness."""

    model_config = STRICT

    session_id: uuid.UUID
    message: str = Field(min_length=1, max_length=4_000)
    loaded_skills: list[SkillId] = Field(default_factory=list, max_length=20)
    uploaded_files: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    channel: Literal["web"] = "web"

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message cannot contain only whitespace")
        return normalized


class SessionCreateRequest(BaseModel):
    """Create a tenant-scoped conversation, optionally with a client UUID."""

    model_config = STRICT

    session_id: uuid.UUID | None = None


class SessionRead(BaseModel):
    """Public session metadata without encrypted internal context."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: str
    status: Literal["active", "archived", "deleted"]
    created_at: datetime
    updated_at: datetime


class ChatMessageRead(BaseModel):
    """Decrypted message visible only to its authenticated owner."""

    model_config = STRICT

    id: uuid.UUID
    trace_id: str | None
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=50_000)
    citations: list[Citation] = Field(default_factory=list, max_length=50)
    created_at: datetime


class SessionMessagesRead(BaseModel):
    """One bounded page of session history."""

    model_config = STRICT

    session_id: uuid.UUID
    messages: list[ChatMessageRead]


class ChatDoneData(BaseModel):
    """Terminal successful SSE payload emitted only after durable persistence."""

    model_config = STRICT

    full_text: str = Field(min_length=1, max_length=50_000)
    references: list[Citation] = Field(default_factory=list, max_length=50)
    safety: SafetyDecision
    trace_id: str
    session_id: uuid.UUID
    replayed: bool = False


class ChatErrorData(BaseModel):
    """Safe terminal failure payload with no provider response text."""

    model_config = STRICT

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    message: str = Field(min_length=1, max_length=500)
    trace_id: str
    retriable: bool

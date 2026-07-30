"""Strict chat, session, and SSE contracts for the Agent Harness boundary."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gerclaw_api.modules.contracts import Citation
from gerclaw_api.modules.input_output import ImageInput
from gerclaw_api.modules.skill.models import SkillId
from gerclaw_api.modules.validation import PublicChatDoneData
from gerclaw_api.modules.workflows import (
    WorkflowContextError,
    WorkflowId,
    get_default_workflow_registry,
)

STRICT = ConfigDict(extra="forbid")


class ChatRequest(BaseModel):
    """One bounded user turn sent to the production Agent Harness."""

    model_config = STRICT

    session_id: uuid.UUID
    message: str = Field(min_length=1, max_length=4_000)
    loaded_skills: list[SkillId] = Field(default_factory=list, max_length=20)
    requested_capabilities: list[str] = Field(default_factory=list, max_length=20)
    uploaded_files: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    images: list[ImageInput] = Field(default_factory=list, max_length=10)
    channel: Literal["web"] = "web"
    workflow: WorkflowId = WorkflowId.STANDARD
    regenerate_from_run_id: uuid.UUID | None = None
    expected_current_answer_version_id: uuid.UUID | None = None

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message cannot contain only whitespace")
        return normalized

    @field_validator("requested_capabilities")
    @classmethod
    def validate_requested_capabilities(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("requested capabilities must be unique")
        for capability_id in value:
            if not 2 <= len(capability_id) <= 128 or not capability_id.startswith("gerclaw."):
                raise ValueError("requested capability id is invalid")
        return value

    @model_validator(mode="after")
    def validate_workflow_context(self) -> ChatRequest:
        """Use the Runtime-owned workflow policy instead of UI-local branching."""

        try:
            get_default_workflow_registry().validate_context(
                self.workflow,
                loaded_skill_count=len(self.loaded_skills),
                uploaded_file_count=len(self.uploaded_files),
                uploaded_image_count=len(self.images),
            )
        except WorkflowContextError as error:
            raise ValueError(str(error)) from error
        if (self.regenerate_from_run_id is None) != (
            self.expected_current_answer_version_id is None
        ):
            raise ValueError(
                "regenerate_from_run_id and expected_current_answer_version_id "
                "must be provided together"
            )
        return self


class SessionCreateRequest(BaseModel):
    """Create a tenant-scoped conversation, optionally with a client UUID."""

    model_config = STRICT

    session_id: uuid.UUID | None = None


class SessionRead(BaseModel):
    """Public session metadata without encrypted internal context."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    agent_id: str
    status: Literal["active", "archived", "deleted"]
    title: str | None = Field(default=None, max_length=120)
    # A metadata-only restore hint. It discloses neither report contents nor
    # clinical intake data, and is always calculated inside the owner scope.
    has_prescription_draft: bool = False
    created_at: datetime
    updated_at: datetime


class SessionListRead(BaseModel):
    """Bounded newest-first session metadata for one persistent account."""

    model_config = STRICT

    sessions: list[SessionRead] = Field(default_factory=list, max_length=50)


class SessionDeleted(BaseModel):
    """Irreversible owner-scoped deletion acknowledgement without session contents."""

    model_config = STRICT

    session_id: uuid.UUID
    deleted: Literal[True] = True


class ChatMessageRead(BaseModel):
    """Decrypted message visible only to its authenticated owner."""

    model_config = STRICT

    id: uuid.UUID
    trace_id: str | None
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=50_000)
    citations: list[Citation] = Field(default_factory=list, max_length=50)
    answer_group_run_id: uuid.UUID | None = None
    answer_version_id: uuid.UUID | None = None
    answer_version: int | None = Field(default=None, ge=1)
    created_at: datetime


class SessionMessagesRead(BaseModel):
    """One bounded page of session history."""

    model_config = STRICT

    session_id: uuid.UUID
    messages: list[ChatMessageRead]


ChatDoneData = PublicChatDoneData


class ChatErrorData(BaseModel):
    """Safe terminal failure payload with no provider response text."""

    model_config = STRICT

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    message: str = Field(min_length=1, max_length=500)
    trace_id: str
    retriable: bool


class ChatCancelledData(BaseModel):
    """Terminal SSE acknowledgement emitted after durable cancellation cleanup."""

    model_config = STRICT

    trace_id: str
    status: Literal["cancelled"] = "cancelled"
    message: str = "回答已停止。未完成内容不代表完整评估结果。"


class ChatInterruptedData(BaseModel):
    """Control-only SSE terminal for an execution replaced by a successor."""

    model_config = STRICT

    trace_id: str
    status: Literal["interrupted"] = "interrupted"
    message: str = "已按新要求调整执行。"


class ChatCancelRead(BaseModel):
    """Accepted identity-scoped request to cancel an active or starting turn."""

    model_config = STRICT

    trace_id: str
    status: Literal["cancellation_requested"] = "cancellation_requested"

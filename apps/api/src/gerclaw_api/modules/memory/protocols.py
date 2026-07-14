"""Chapter 4.8 short-term, long-term, extraction, and compression boundary."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.security import JsonValue

MemoryRole = Literal["user", "assistant", "system", "tool"]
MemoryCategory = Literal[
    "basic_info",
    "allergy",
    "condition",
    "medication",
    "vital_sign",
    "assessment",
    "event",
    "social",
    "preference",
    "goal",
]
MemoryType = Literal["stable", "evolving", "event"]
MemoryStatus = Literal["confirmed", "pending", "inactive"]


class MemoryMessage(BaseModel):
    """One bounded message at the Memory Protocol boundary."""

    model_config = ConfigDict(extra="forbid")

    role: MemoryRole
    content: list[dict[str, JsonValue]] = Field(min_length=1, max_length=50)

    def text(self) -> str:
        """Project validated text blocks without accepting arbitrary objects."""

        parts: list[str] = []
        for block in self.content:
            if block.get("type") != "text":
                continue
            value = block.get("text")
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        return "\n".join(parts)


class MemoryFactView(BaseModel):
    """Decrypted fact returned only after tenant/user and vector-version checks."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    category: MemoryCategory
    memory_type: MemoryType
    status: MemoryStatus
    statement: str = Field(min_length=1, max_length=1_000)
    details: dict[str, JsonValue]
    confidence: float = Field(ge=0, le=1)
    revision: int = Field(ge=1)
    source_trace_id: str | None = Field(default=None, max_length=64)
    occurred_at: datetime | None = None
    confirmed_at: datetime | None = None
    updated_at: datetime
    relevance_score: float | None = Field(default=None, ge=0, le=1)


class UserProfile(BaseModel):
    """Structured core profile plus optional relevance-filtered facts."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    version: int = Field(ge=0)
    profile: dict[str, JsonValue]
    provenance_refs: list[str] = Field(default_factory=list, max_length=200)
    relevant_facts: list[MemoryFactView] = Field(default_factory=list, max_length=50)


class MemoryModule(Protocol):
    """Memory contract matching all methods required by design §4.8."""

    async def get_short_term(self, session_id: str, max_turns: int = 20) -> list[MemoryMessage]:
        """Load ordered short-term conversation memory."""

    async def get_long_term(self, user_id: str, query: str | None = None) -> UserProfile:
        """Load structured and relevance-filtered long-term memory."""

    async def save_message(self, session_id: str, message: MemoryMessage) -> None:
        """Persist one encrypted message."""

    async def extract_and_update_profile(
        self, user_id: str, conversation: list[MemoryMessage]
    ) -> None:
        """Extract evidenced profile changes from a conversation."""

    async def compress_context(
        self, messages: list[MemoryMessage], max_tokens: int
    ) -> list[MemoryMessage]:
        """Compress context while preserving clinically relevant evidence."""

"""Chapter 4.8 short-term, long-term, extraction, and compression interface."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.security import JsonValue


class MemoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant", "system", "tool"]
    content: list[dict[str, JsonValue]] = Field(max_length=50)


class UserProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    profile: dict[str, JsonValue]
    provenance_refs: list[str] = Field(default_factory=list, max_length=200)


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

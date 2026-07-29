"""Validated context supplied to one isolated AgentScope turn."""

from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from gerclaw_api.modules.contracts import ExecutionContext

BoundedReference = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]


class ConversationHistoryMessage(BaseModel):
    """Bounded decrypted history supplied to an isolated AgentScope state."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=50_000)


class AgentContext(BaseModel):
    """Validated context snapshot assembled before entering the ReAct loop."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    execution: ExecutionContext
    system_instructions: list[BoundedReference] = Field(max_length=20)
    tool_names: list[BoundedReference] = Field(max_length=100)
    profile_ref: BoundedReference | None = None
    profile_context: str = Field(default="", max_length=20_000)
    profile_version: int = Field(default=0, ge=0)
    memory_refs: list[BoundedReference] = Field(default_factory=list, max_length=100)
    session_summary: str = Field(default="", max_length=20_000)
    loaded_skills: list[BoundedReference] = Field(default_factory=list, max_length=50)
    uploaded_files: list[BoundedReference] = Field(default_factory=list, max_length=20)
    conversation_history: list[ConversationHistoryMessage] = Field(
        default_factory=list, max_length=200
    )


class ContextSnapshotError(RuntimeError):
    """Stable context assembly failure."""


class ContextSnapshotAssembler(Protocol):
    def assemble(
        self,
        *,
        execution: ExecutionContext,
        history: tuple[ConversationHistoryMessage, ...],
    ) -> AgentContext:
        """Build one actor-scoped, bounded immutable snapshot."""

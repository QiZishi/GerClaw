"""Validated context supplied to one isolated AgentScope turn."""

from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from gerclaw_api.modules.agent_harness.clinical_state import ClinicalState
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
    clinical_state: ClinicalState = Field(default_factory=ClinicalState)
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
        system_instructions: tuple[str, ...],
        tool_names: tuple[str, ...],
        profile_ref: str | None,
        profile_context: str,
        profile_version: int,
        memory_refs: tuple[str, ...],
        session_summary: str,
        clinical_state: ClinicalState,
        loaded_skills: tuple[str, ...],
        uploaded_files: tuple[str, ...],
    ) -> AgentContext:
        """Build one actor-scoped, bounded immutable snapshot."""


class ProductionContextSnapshotAssembler:
    """Construct the validated immutable snapshot from already scoped inputs."""

    def assemble(
        self,
        *,
        execution: ExecutionContext,
        history: tuple[ConversationHistoryMessage, ...],
        system_instructions: tuple[str, ...],
        tool_names: tuple[str, ...],
        profile_ref: str | None,
        profile_context: str,
        profile_version: int,
        memory_refs: tuple[str, ...],
        session_summary: str,
        clinical_state: ClinicalState,
        loaded_skills: tuple[str, ...],
        uploaded_files: tuple[str, ...],
    ) -> AgentContext:
        return AgentContext(
            execution=execution,
            system_instructions=list(system_instructions),
            tool_names=list(tool_names),
            profile_ref=profile_ref,
            profile_context=profile_context,
            profile_version=profile_version,
            memory_refs=list(memory_refs),
            session_summary=session_summary,
            clinical_state=clinical_state,
            loaded_skills=list(loaded_skills),
            uploaded_files=list(uploaded_files),
            conversation_history=list(history),
        )

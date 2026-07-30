"""Validated context supplied to one isolated AgentScope turn."""

from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from gerclaw_api.modules.agent_harness.clinical_state import ClinicalState
from gerclaw_api.modules.contracts import ExecutionContext

BoundedReference = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]


class ConversationHistoryMessage(BaseModel):
    """Bounded decrypted history supplied to an isolated AgentScope state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=50_000)


class ContextSourceBudget(BaseModel):
    """Content-free token accounting for one model-visible context source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal[
        "system_tools",
        "current_input",
        "profile",
        "clinical_state",
        "skills",
        "documents",
        "capability_results",
        "plan",
        "history",
        "history_summary",
        "images",
        "evidence_reserve",
    ]
    policy: Literal["required", "compressible", "bounded_reserve"]
    estimated_tokens: int = Field(ge=0, le=1_000_000)


class ContextProjectionManifest(BaseModel):
    """Auditable, content-free record of pre-model context window management."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["context-projection-v1"] = "context-projection-v1"
    projection_mode: Literal["model_call", "deterministic_short_circuit"] = "model_call"
    model_context_tokens: int = Field(ge=1, le=10_000_000)
    trigger_tokens: int = Field(ge=1, le=10_000_000)
    target_tokens: int = Field(ge=1, le=10_000_000)
    output_reserve_tokens: int = Field(ge=1, le=1_000_000)
    estimated_tokens_before: int = Field(ge=0, le=10_000_000)
    estimated_tokens_after: int = Field(ge=0, le=10_000_000)
    history_budget_tokens: int = Field(ge=0, le=10_000_000)
    history_message_count: int = Field(ge=0, le=200)
    retained_history_message_count: int = Field(ge=0, le=200)
    compression_state: Literal["not_needed", "compressed"]
    compression_strategy: Literal[
        "none",
        "agentscope-medical-summary-v1",
        "deterministic-extractive-v1",
    ]
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    sections: tuple[ContextSourceBudget, ...] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_projection(self) -> "ContextProjectionManifest":
        if not self.target_tokens <= self.trigger_tokens <= self.model_context_tokens:
            raise ValueError("context projection thresholds are inconsistent")
        if (
            self.projection_mode == "model_call"
            and self.estimated_tokens_after > self.trigger_tokens
        ):
            raise ValueError("projected context still exceeds its trigger")
        if self.retained_history_message_count > self.history_message_count:
            raise ValueError("retained history count exceeds source count")
        sources = [item.source for item in self.sections]
        if len(sources) != len(set(sources)):
            raise ValueError("context projection contains duplicate sources")
        if (self.compression_state == "not_needed") != (self.compression_strategy == "none"):
            raise ValueError("context compression state and strategy disagree")
        return self


class AgentContext(BaseModel):
    """Validated context snapshot assembled before entering the ReAct loop."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    execution: ExecutionContext
    system_instructions: tuple[BoundedReference, ...] = Field(max_length=20)
    tool_names: tuple[BoundedReference, ...] = Field(max_length=100)
    profile_ref: BoundedReference | None = None
    profile_context: str = Field(default="", max_length=20_000)
    profile_version: int = Field(default=0, ge=0)
    memory_refs: tuple[BoundedReference, ...] = Field(default=(), max_length=100)
    session_summary: str = Field(default="", max_length=20_000)
    clinical_state: ClinicalState = Field(default_factory=ClinicalState)
    loaded_skills: tuple[BoundedReference, ...] = Field(default=(), max_length=50)
    uploaded_files: tuple[BoundedReference, ...] = Field(default=(), max_length=20)
    conversation_history: tuple[ConversationHistoryMessage, ...] = Field(default=(), max_length=200)
    projection: ContextProjectionManifest | None = None


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
            system_instructions=system_instructions,
            tool_names=tool_names,
            profile_ref=profile_ref,
            profile_context=profile_context,
            profile_version=profile_version,
            memory_refs=memory_refs,
            session_summary=session_summary,
            clinical_state=clinical_state,
            loaded_skills=loaded_skills,
            uploaded_files=uploaded_files,
            conversation_history=history,
        )

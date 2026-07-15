"""Strict Skill DTOs shared by storage, APIs, and AgentScope adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from gerclaw_api.security import JsonValue, redact_text

STRICT = ConfigDict(extra="forbid")


def _phi_free_skill_id(value: str) -> str:
    if redact_text(value) != value:
        raise ValueError("Skill ids cannot contain personal or secret identifiers")
    return value


SkillId = Annotated[
    str,
    Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$"),
    AfterValidator(_phi_free_skill_id),
]
SkillVersion = Annotated[str, Field(pattern=r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")]
ToolName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")]


class SkillInfo(BaseModel):
    """Public metadata for a system or caller-owned Skill."""

    model_config = STRICT

    skill_id: SkillId
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    version: SkillVersion
    parameter_schema: dict[str, JsonValue]
    tool_names: list[ToolName] = Field(default_factory=list, max_length=20)
    category: str = Field(default="general", min_length=1, max_length=32)
    source: Literal["builtin", "custom"]
    origin: Literal["builtin", "text", "upload", "generated"]
    enabled: bool
    revision: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("name", "description", "category")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Skill metadata cannot contain only whitespace")
        return normalized

    @field_validator("tool_names")
    @classmethod
    def unique_tools(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Skill tools must be unique")
        return value


class SkillDefinition(SkillInfo):
    """Complete versioned Skill definition after trust-boundary validation."""

    source_markdown: str = Field(min_length=1, max_length=10_000)


class Skill(BaseModel):
    """Loaded Skill plus its allowlisted tool capability declaration."""

    model_config = STRICT

    definition: SkillDefinition
    tool_names: list[ToolName] = Field(max_length=20)

    @model_validator(mode="after")
    def tools_match_definition(self) -> Skill:
        if self.tool_names != self.definition.tool_names:
            raise ValueError("loaded Skill tools do not match its definition")
        return self


class SkillResult(BaseModel):
    """Auditable activation result; public medical generation stays in Agent Harness."""

    model_config = STRICT

    ok: bool
    output: dict[str, JsonValue] = Field(default_factory=dict)
    error_code: str | None = Field(default=None, max_length=64)


class SkillDraftRequest(BaseModel):
    """Natural-language request used only to generate a reviewable draft."""

    model_config = STRICT

    description: str = Field(min_length=10, max_length=2_000)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("description cannot contain only whitespace")
        return normalized


class GeneratedSkillContent(BaseModel):
    """Structured model response before deterministic Markdown serialization."""

    model_config = STRICT

    skill_id: SkillId
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    version: SkillVersion = "1.0.0"
    category: str = Field(min_length=1, max_length=32)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    tools: list[ToolName] = Field(default_factory=list, max_length=20)
    instructions: str = Field(min_length=20, max_length=8_000)


class SkillRegisterRequest(BaseModel):
    """Register an already reviewed Skill Markdown document."""

    model_config = STRICT

    source_markdown: str = Field(min_length=1, max_length=10_000)
    origin: Literal["text", "upload", "generated"] = "text"


class SkillUpdateRequest(BaseModel):
    """Replace caller-owned Skill content with optimistic revision control."""

    model_config = STRICT

    source_markdown: str | None = Field(default=None, min_length=1, max_length=10_000)
    enabled: bool | None = None
    expected_revision: int = Field(ge=1)

    @model_validator(mode="after")
    def require_change(self) -> SkillUpdateRequest:
        if self.source_markdown is None and self.enabled is None:
            raise ValueError("at least one Skill field must change")
        return self


class SkillExecuteRequest(BaseModel):
    """Bounded parameter payload for explicit Skill activation."""

    model_config = STRICT

    params: dict[str, JsonValue] = Field(default_factory=dict)


class SessionSkillsRequest(BaseModel):
    """Ordered Skill selection persisted for one caller-owned conversation."""

    model_config = STRICT

    skill_ids: list[SkillId] = Field(default_factory=list, max_length=10)

    @field_validator("skill_ids")
    @classmethod
    def unique_skill_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("loaded Skill ids must be unique")
        return value


class SessionSkillsRead(SessionSkillsRequest):
    """Current persisted Skill selection."""

    session_id: str

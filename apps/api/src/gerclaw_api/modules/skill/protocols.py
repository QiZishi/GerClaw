"""Chapter 4.9 skill discovery, registration, loading, execution, and generation interface."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.security import JsonValue


class SkillInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_id: str
    name: str
    description: str
    version: str
    parameter_schema: dict[str, JsonValue]


class SkillDefinition(SkillInfo):
    source_markdown: str = Field(min_length=1, max_length=100_000)


class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: SkillDefinition
    tool_names: list[str] = Field(max_length=100)


class SkillResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    output: dict[str, JsonValue] = Field(default_factory=dict)
    error_code: str | None = None


class SkillModule(Protocol):
    """Skill contract matching every operation required by design §4.9."""

    async def list_skills(self, user_id: str | None = None) -> list[SkillInfo]:
        """Discover system and optional user skills."""

    async def load_skill(self, skill_id: str) -> Skill:
        """Load and validate one skill definition."""

    async def register_skill(self, skill_definition: SkillDefinition) -> str:
        """Register a versioned, policy-checked skill."""

    async def execute_skill(self, skill_id: str, params: dict[str, JsonValue]) -> SkillResult:
        """Execute a loaded skill through the tool policy layer."""

    async def generate_skill_from_nl(self, description: str) -> SkillDefinition:
        """Generate a definition for review; registration remains explicit."""

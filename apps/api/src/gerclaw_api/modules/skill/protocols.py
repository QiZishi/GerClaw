"""Chapter 4.9 Skill discovery, registration, loading, execution, and generation interface."""

from __future__ import annotations

from typing import Protocol

from gerclaw_api.modules.skill.models import Skill, SkillDefinition, SkillInfo, SkillResult
from gerclaw_api.security import JsonValue


class SkillModule(Protocol):
    """Skill contract matching every operation required by design §4.9."""

    async def list_skills(self, user_id: str | None = None) -> list[SkillInfo]:
        """Discover system and optional user Skills."""

    async def load_skill(self, skill_id: str) -> Skill:
        """Load and validate one Skill definition."""

    async def register_skill(self, skill_definition: SkillDefinition) -> str:
        """Register a versioned, policy-checked Skill."""

    async def execute_skill(self, skill_id: str, params: dict[str, JsonValue]) -> SkillResult:
        """Validate and activate a Skill through the AgentScope policy layer."""

    async def generate_skill_from_nl(self, description: str) -> SkillDefinition:
        """Generate a definition for review; registration remains explicit."""


__all__ = [
    "Skill",
    "SkillDefinition",
    "SkillInfo",
    "SkillModule",
    "SkillResult",
]

"""System Skill discovery using AgentScope's real LocalSkillLoader."""

from __future__ import annotations

from pathlib import Path

from agentscope.skill import LocalSkillLoader

from gerclaw_api.modules.skill.loader import parse_skill_markdown
from gerclaw_api.modules.skill.models import SkillDefinition


class BuiltinSkillRegistryError(RuntimeError):
    """Raised when packaged immutable Skills fail integrity checks."""


class BuiltinSkillRegistry:
    """Discover packaged Skills and cross-check them with AgentScope 2.0.4."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or Path(__file__).resolve().parent / "builtin"
        self._agentscope_loader = LocalSkillLoader(str(self.directory), scan_subdir=True)

    async def list_definitions(self) -> list[SkillDefinition]:
        agent_skills = await self._agentscope_loader.list_skills()
        definitions: list[SkillDefinition] = []
        for path in sorted(self.directory.glob("*/SKILL.md")):
            definition = parse_skill_markdown(
                path.read_text(encoding="utf-8"),
                source="builtin",
                origin="builtin",
            )
            definitions.append(definition)
        if not definitions:
            raise BuiltinSkillRegistryError("no packaged Skills were found")
        if {item.name for item in agent_skills} != {item.name for item in definitions}:
            raise BuiltinSkillRegistryError("AgentScope and GerClaw Skill discovery disagree")
        ids = [item.skill_id for item in definitions]
        names = [item.name for item in definitions]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise BuiltinSkillRegistryError("packaged Skill ids and names must be unique")
        return definitions

    async def get(self, skill_id: str) -> SkillDefinition | None:
        return next(
            (item for item in await self.list_definitions() if item.skill_id == skill_id),
            None,
        )

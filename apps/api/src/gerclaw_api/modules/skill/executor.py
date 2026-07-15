"""Bounded AgentScope activation for validated declarative Skills."""

from __future__ import annotations

from agentscope.tool import Toolkit

from gerclaw_api.modules.skill.agentscope_adapter import (
    SAFE_SKILL_INSTRUCTION_TEMPLATE,
    to_agentscope_skill,
)
from gerclaw_api.modules.skill.loader import SkillFormatError, validate_skill_params
from gerclaw_api.modules.skill.models import SkillDefinition, SkillResult
from gerclaw_api.security import JsonValue


class SkillExecutor:
    """Validate parameters and prove the Skill is activatable by AgentScope Toolkit."""

    async def execute(
        self, definition: SkillDefinition, params: dict[str, JsonValue]
    ) -> SkillResult:
        try:
            validated = validate_skill_params(definition, params)
            toolkit = Toolkit(
                skills_or_loaders=[to_agentscope_skill(definition)],
                skill_instruction_template=SAFE_SKILL_INSTRUCTION_TEMPLATE,
            )
            instructions = await toolkit.get_skill_instructions()
            schemas = await toolkit.get_tool_schemas()
            if (
                instructions is None
                or definition.name not in instructions
                or not any(schema.get("function", {}).get("name") == "Skill" for schema in schemas)
            ):
                raise RuntimeError("AgentScope did not activate the Skill viewer")
            return SkillResult(
                ok=True,
                output={
                    "skill_id": definition.skill_id,
                    "version": definition.version,
                    "revision": definition.revision,
                    "parameter_names": list(validated),
                    "tool_names": list(definition.tool_names),
                    "agentscope_activated": True,
                },
            )
        except SkillFormatError:
            return SkillResult(ok=False, error_code="SKILL_PARAMETER_INVALID")

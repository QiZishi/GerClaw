"""Production tenant-scoped implementation of design requirement §4.9."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

from agentscope.skill import Skill as AgentScopeSkill

from gerclaw_api.modules.skill.agentscope_adapter import to_agentscope_skill
from gerclaw_api.modules.skill.executor import SkillExecutor
from gerclaw_api.modules.skill.generator import RealSkillGenerator, StructuredSkillModel
from gerclaw_api.modules.skill.loader import DEFAULT_ALLOWED_TOOLS, parse_skill_markdown
from gerclaw_api.modules.skill.models import Skill, SkillDefinition, SkillInfo, SkillResult
from gerclaw_api.modules.skill.registry import BuiltinSkillRegistry
from gerclaw_api.modules.skill.security import enforce_skill_runtime_profile
from gerclaw_api.security import JsonValue

if TYPE_CHECKING:
    from gerclaw_api.repositories.skill import SqlAlchemySkillRepository


class SkillNotFoundError(LookupError):
    """Raised when the caller cannot access a Skill."""


class SkillDisabledError(RuntimeError):
    """Raised when execution is attempted on a disabled custom Skill."""


class SkillConflictError(RuntimeError):
    """Raised when a custom Skill conflicts with a system or caller Skill."""


class CorruptSkillError(RuntimeError):
    """Raised instead of loading invalid encrypted database content into an Agent."""


class ProductionSkillModule:
    """Request-scoped Skill service over immutable builtins and encrypted custom records."""

    def __init__(
        self,
        *,
        repository: SqlAlchemySkillRepository,
        tenant_id: str,
        actor_id: str,
        model: StructuredSkillModel | None = None,
        builtins: BuiltinSkillRegistry | None = None,
        executor: SkillExecutor | None = None,
        allowed_tools: frozenset[str] = DEFAULT_ALLOWED_TOOLS,
    ) -> None:
        self._repository = repository
        self._tenant_id = tenant_id
        self._actor_id = actor_id
        self._generator = RealSkillGenerator(model) if model is not None else None
        self._builtins = builtins or BuiltinSkillRegistry()
        self._executor = executor or SkillExecutor()
        self._allowed_tools = allowed_tools

    async def list_skills(self, user_id: str | None = None) -> list[SkillInfo]:
        if user_id is not None and user_id != self._actor_id:
            raise SkillNotFoundError("Skill owner is not accessible")
        builtins = await self._builtins.list_definitions()
        custom = [
            self._definition_from_record(item)
            for item in await self._repository.list_custom(
                tenant_id=self._tenant_id, actor_id=self._actor_id
            )
        ]
        return [
            SkillInfo.model_validate(item.model_dump(exclude={"source_markdown"}))
            for item in [
                *builtins,
                *custom,
            ]
        ]

    async def load_skill(self, skill_id: str) -> Skill:
        definition = await self._builtins.get(skill_id)
        if definition is None:
            record = await self._repository.get_custom(
                skill_id, tenant_id=self._tenant_id, actor_id=self._actor_id
            )
            if record is None:
                raise SkillNotFoundError("Skill not found")
            definition = self._definition_from_record(record)
        return Skill(definition=definition, tool_names=definition.tool_names)

    async def load_enabled_skill(self, skill_id: str) -> Skill:
        skill = await self.load_skill(skill_id)
        if not skill.definition.enabled:
            raise SkillDisabledError("Skill is disabled")
        enforce_skill_runtime_profile(skill.definition)
        return skill

    async def register_markdown(
        self, source_markdown: str, *, origin: str, commit: bool = True
    ) -> SkillDefinition:
        definition = self.preview_markdown(source_markdown, origin=origin)
        await self.register_skill(definition, commit=commit)
        return (await self.load_skill(definition.skill_id)).definition

    def preview_markdown(self, source_markdown: str, *, origin: str) -> SkillDefinition:
        """Validate a review draft without mutating the registry."""

        return parse_skill_markdown(
            source_markdown,
            source="custom",
            origin=origin,
            allowed_tools=self._allowed_tools,
        )

    async def register_skill(
        self, skill_definition: SkillDefinition, *, commit: bool = True
    ) -> str:
        definition = parse_skill_markdown(
            skill_definition.source_markdown,
            source="custom",
            origin=skill_definition.origin,
            allowed_tools=self._allowed_tools,
        )
        if await self._builtins.get(definition.skill_id) is not None:
            raise SkillConflictError("system Skill ids are reserved")
        existing = await self.list_skills()
        if any(item.name.casefold() == definition.name.casefold() for item in existing):
            raise SkillConflictError("a Skill with this name already exists")
        await self._repository.create_custom(
            definition, tenant_id=self._tenant_id, actor_id=self._actor_id
        )
        if commit:
            await self._repository.commit()
        return definition.skill_id

    async def update_skill(
        self,
        skill_id: str,
        *,
        source_markdown: str | None,
        enabled: bool | None,
        expected_revision: int,
        commit: bool = True,
    ) -> SkillDefinition:
        if await self._builtins.get(skill_id) is not None:
            raise SkillConflictError("system Skills are immutable")
        current_record = await self._repository.get_custom(
            skill_id, tenant_id=self._tenant_id, actor_id=self._actor_id
        )
        if current_record is None:
            raise SkillNotFoundError("Skill not found")
        current = self._definition_from_record(current_record)
        replacement = None
        if source_markdown is not None:
            replacement = parse_skill_markdown(
                source_markdown,
                source="custom",
                origin="text",
                enabled=enabled if enabled is not None else current.enabled,
                revision=expected_revision + 1,
                allowed_tools=self._allowed_tools,
            )
            if replacement.skill_id != skill_id:
                raise SkillConflictError("Skill id cannot change during update")
            if _semantic_version(replacement.version) <= _semantic_version(current.version):
                raise SkillConflictError("Skill behavior changes require a higher Semantic Version")
            existing = await self.list_skills()
            if any(
                item.skill_id != skill_id and item.name.casefold() == replacement.name.casefold()
                for item in existing
            ):
                raise SkillConflictError("a Skill with this name already exists")
        record = await self._repository.update_custom(
            skill_id,
            tenant_id=self._tenant_id,
            actor_id=self._actor_id,
            expected_revision=expected_revision,
            definition=replacement,
            enabled=enabled,
        )
        if record is None:
            raise SkillNotFoundError("Skill not found")
        if commit:
            await self._repository.commit()
        return self._definition_from_record(record)

    async def delete_skill(
        self, skill_id: str, *, expected_revision: int, commit: bool = True
    ) -> None:
        if await self._builtins.get(skill_id) is not None:
            raise SkillConflictError("system Skills are immutable")
        deleted = await self._repository.delete_custom(
            skill_id,
            tenant_id=self._tenant_id,
            actor_id=self._actor_id,
            expected_revision=expected_revision,
        )
        if not deleted:
            raise SkillNotFoundError("Skill not found")
        if commit:
            await self._repository.commit()

    async def execute_skill(self, skill_id: str, params: dict[str, JsonValue]) -> SkillResult:
        skill = await self.load_enabled_skill(skill_id)
        return await self._executor.execute(skill.definition, params)

    async def generate_skill_from_nl(self, description: str) -> SkillDefinition:
        if self._generator is None:
            raise RuntimeError("Skill generation model is unavailable")
        return await self._generator.generate(description)

    async def evolve_skill_from_nl(
        self,
        skill_id: str,
        *,
        change_request: str,
        expected_revision: int,
    ) -> SkillDefinition:
        """Generate a revision draft; saving it remains a separate explicit action."""

        if self._generator is None:
            raise RuntimeError("Skill generation model is unavailable")
        if await self._builtins.get(skill_id) is not None:
            raise SkillConflictError("system Skills are immutable")
        record = await self._repository.get_custom(
            skill_id, tenant_id=self._tenant_id, actor_id=self._actor_id
        )
        if record is None:
            raise SkillNotFoundError("Skill not found")
        current = self._definition_from_record(record)
        if current.revision != expected_revision:
            raise SkillConflictError("Skill revision is stale")
        return await self._generator.evolve(current, change_request)

    async def resolve_agent_skills(self, skill_ids: list[str]) -> list[AgentScopeSkill]:
        skills = [await self.load_enabled_skill(skill_id) for skill_id in skill_ids]
        names = [item.definition.name.casefold() for item in skills]
        if len(names) != len(set(names)):
            raise CorruptSkillError("selected Skills do not have unique names")
        return [to_agentscope_skill(item.definition) for item in skills]

    async def replace_session_skills(
        self, session_id: uuid.UUID, skill_ids: list[str], *, commit: bool = True
    ) -> None:
        for skill_id in skill_ids:
            await self.load_enabled_skill(skill_id)
        await self._repository.replace_session_skills(
            session_id,
            skill_ids,
            tenant_id=self._tenant_id,
            actor_id=self._actor_id,
        )
        if commit:
            await self._repository.commit()

    async def list_session_skills(self, session_id: uuid.UUID) -> list[str]:
        return await self._repository.list_session_skills(
            session_id, tenant_id=self._tenant_id, actor_id=self._actor_id
        )

    def _definition_from_record(self, record: object) -> SkillDefinition:
        try:
            typed = cast("SkillDefinitionRecordLike", record)
            definition = parse_skill_markdown(
                typed.source_markdown,
                source="custom",
                origin=typed.origin,
                enabled=typed.enabled,
                revision=typed.revision,
                allowed_tools=self._allowed_tools,
            )
            return definition.model_copy(
                update={"created_at": typed.created_at, "updated_at": typed.updated_at}
            )
        except Exception as error:
            raise CorruptSkillError("stored Skill failed integrity validation") from error


class SkillDefinitionRecordLike:
    """Structural typing helper kept local to avoid leaking ORM models into the module API."""

    source_markdown: str
    origin: str
    enabled: bool
    revision: int
    created_at: object
    updated_at: object


def _semantic_version(value: str) -> tuple[int, int, int]:
    """Compare the already schema-validated SemVer form without a new dependency."""

    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)

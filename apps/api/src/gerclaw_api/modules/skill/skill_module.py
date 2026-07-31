"""Production tenant-scoped implementation of design requirement §4.9."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, cast

from agentscope.skill import Skill as AgentScopeSkill

from gerclaw_api.modules.skill.agentscope_adapter import to_agentscope_skill
from gerclaw_api.modules.skill.evolution_policy import SkillEvolutionPolicy
from gerclaw_api.modules.skill.executor import SkillExecutor
from gerclaw_api.modules.skill.generator import RealSkillGenerator, StructuredSkillModel
from gerclaw_api.modules.skill.loader import DEFAULT_ALLOWED_TOOLS, parse_skill_markdown
from gerclaw_api.modules.skill.models import (
    Skill,
    SkillDefinition,
    SkillEvolutionOutcome,
    SkillEvolutionProposalReceipt,
    SkillInfo,
    SkillResult,
)
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


_PENDING_OFFLINE_CATEGORY = "offline_pending"


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
        evolution_policy: SkillEvolutionPolicy | None = None,
        allowed_tools: frozenset[str] = DEFAULT_ALLOWED_TOOLS,
    ) -> None:
        self._repository = repository
        self._tenant_id = tenant_id
        self._actor_id = actor_id
        self._generator = RealSkillGenerator(model) if model is not None else None
        self._builtins = builtins or BuiltinSkillRegistry()
        self._executor = executor or SkillExecutor()
        self._evolution_policy = evolution_policy or SkillEvolutionPolicy()
        self._allowed_tools = allowed_tools

    async def list_skills(self, user_id: str | None = None) -> list[SkillInfo]:
        if user_id is not None and user_id != self._actor_id:
            raise SkillNotFoundError("Skill owner is not accessible")
        builtins = await self._builtins.list_definitions()
        custom = []
        for item in await self._repository.list_custom(
            tenant_id=self._tenant_id, actor_id=self._actor_id
        ):
            definition = self._definition_from_record(item)
            if not _is_pending_placeholder(definition):
                custom.append(definition)
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
            if _is_pending_placeholder(definition):
                raise SkillNotFoundError("Skill not found")
        return Skill(definition=definition, tool_names=definition.tool_names)

    async def load_enabled_skill(self, skill_id: str) -> Skill:
        skill = await self.load_skill(skill_id)
        if not skill.definition.enabled:
            raise SkillDisabledError("Skill is disabled")
        enforce_skill_runtime_profile(skill.definition)
        return skill

    async def register_markdown(
        self,
        source_markdown: str,
        *,
        origin: str,
        proposal_trace_id: str | None = None,
        request_fingerprint: str | None = None,
        commit: bool = True,
    ) -> SkillDefinition | SkillEvolutionOutcome:
        definition = self.preview_markdown(source_markdown, origin=origin)
        return await self.register_skill(
            definition,
            proposal_trace_id=proposal_trace_id,
            request_fingerprint=request_fingerprint,
            commit=commit,
        )

    def preview_markdown(self, source_markdown: str, *, origin: str) -> SkillDefinition:
        """Validate a review draft without mutating the registry."""

        return parse_skill_markdown(
            source_markdown,
            source="custom",
            origin=origin,
            allowed_tools=self._allowed_tools,
        )

    async def register_skill(
        self,
        skill_definition: SkillDefinition,
        *,
        proposal_trace_id: str | None = None,
        request_fingerprint: str | None = None,
        commit: bool = True,
    ) -> SkillDefinition | SkillEvolutionOutcome:
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
        if not self._evolution_policy.online_registration_allowed(definition):
            self._validate_provenance(proposal_trace_id, request_fingerprint)
            placeholder = parse_skill_markdown(
                _pending_placeholder_markdown(definition),
                source="custom",
                origin="generated",
                enabled=False,
                revision=1,
                allowed_tools=self._allowed_tools,
            )
            candidate = definition.model_copy(update={"revision": 2})
            decision = self._evolution_policy.decide(
                placeholder,
                candidate,
                expected_revision=1,
                apply_if_low_risk=True,
            )
            if decision.disposition != "offline_review_required":
                raise SkillConflictError("Skill registration policy is inconsistent")
            await self._repository.create_custom(
                placeholder,
                tenant_id=self._tenant_id,
                actor_id=self._actor_id,
            )
            proposal = await self._repository.create_evolution_proposal(
                definition.skill_id,
                tenant_id=self._tenant_id,
                actor_id=self._actor_id,
                expected_revision=1,
                current=placeholder,
                candidate=candidate,
                decision=decision,
                change_request="initial_skill_registration",
                trace_id=proposal_trace_id or "",
                request_fingerprint=request_fingerprint or "",
            )
            if commit:
                await self._repository.commit()
            return SkillEvolutionOutcome(
                candidate=candidate,
                decision=decision,
                offline_proposal_receipt=_proposal_receipt(proposal),
            )
        await self._repository.create_custom(
            definition, tenant_id=self._tenant_id, actor_id=self._actor_id
        )
        if commit:
            await self._repository.commit()
        return (await self.load_skill(definition.skill_id)).definition

    async def update_skill(
        self,
        skill_id: str,
        *,
        source_markdown: str | None,
        enabled: bool | None,
        expected_revision: int,
        proposal_trace_id: str | None = None,
        request_fingerprint: str | None = None,
        commit: bool = True,
    ) -> SkillDefinition | SkillEvolutionOutcome:
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
            decision = self._evolution_policy.decide(
                current,
                replacement,
                expected_revision=expected_revision,
                apply_if_low_risk=True,
            )
            if decision.disposition == "offline_review_required":
                self._validate_provenance(proposal_trace_id, request_fingerprint)
                proposal = await self._repository.create_evolution_proposal(
                    skill_id,
                    tenant_id=self._tenant_id,
                    actor_id=self._actor_id,
                    expected_revision=expected_revision,
                    current=current,
                    candidate=replacement,
                    decision=decision,
                    change_request="manual_skill_revision",
                    trace_id=proposal_trace_id or "",
                    request_fingerprint=request_fingerprint or "",
                )
                if commit:
                    await self._repository.commit()
                return SkillEvolutionOutcome(
                    candidate=replacement,
                    decision=decision,
                    offline_proposal_receipt=_proposal_receipt(proposal),
                )
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

    @staticmethod
    def _validate_provenance(
        proposal_trace_id: str | None,
        request_fingerprint: str | None,
    ) -> None:
        if not proposal_trace_id or len(proposal_trace_id) > 128:
            raise SkillConflictError("Skill offline review requires valid request provenance")
        if (
            request_fingerprint is None
            or re.fullmatch(r"(?:[a-f0-9]{64}|[a-z2-7]{52})", request_fingerprint) is None
        ):
            raise SkillConflictError("Skill offline review requires valid request provenance")

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
        proposal_trace_id: str,
        request_fingerprint: str,
        apply_if_low_risk: bool = True,
        commit: bool = True,
    ) -> SkillEvolutionOutcome:
        """Apply only low-authority revisions; return dangerous changes as offline proposals."""

        self._validate_provenance(proposal_trace_id, request_fingerprint)
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
        generated = await self._generator.evolve(current, change_request)
        candidate = parse_skill_markdown(
            generated.source_markdown,
            source="custom",
            origin="generated",
            enabled=current.enabled,
            revision=expected_revision + 1,
            allowed_tools=self._allowed_tools,
        )
        decision = self._evolution_policy.decide(
            current,
            candidate,
            expected_revision=expected_revision,
            apply_if_low_risk=apply_if_low_risk,
        )
        if decision.disposition != "online_applied":
            proposal_receipt = None
            if decision.disposition == "offline_review_required":
                proposal = await self._repository.create_evolution_proposal(
                    skill_id,
                    tenant_id=self._tenant_id,
                    actor_id=self._actor_id,
                    expected_revision=expected_revision,
                    current=current,
                    candidate=candidate,
                    decision=decision,
                    change_request=change_request,
                    trace_id=proposal_trace_id,
                    request_fingerprint=request_fingerprint,
                )
                proposal_receipt = _proposal_receipt(proposal)
                if commit:
                    await self._repository.commit()
            return SkillEvolutionOutcome(
                candidate=candidate,
                decision=decision,
                offline_proposal_receipt=proposal_receipt,
            )

        existing = await self.list_skills()
        if any(
            item.skill_id != skill_id and item.name.casefold() == candidate.name.casefold()
            for item in existing
        ):
            raise SkillConflictError("a Skill with this name already exists")
        updated_record = await self._repository.update_custom(
            skill_id,
            tenant_id=self._tenant_id,
            actor_id=self._actor_id,
            expected_revision=expected_revision,
            definition=candidate,
            enabled=current.enabled,
        )
        if updated_record is None:
            raise SkillNotFoundError("Skill not found")
        if commit:
            await self._repository.commit()
        active = self._definition_from_record(updated_record)
        return SkillEvolutionOutcome(
            candidate=candidate,
            decision=decision,
            active_definition=active,
        )

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


def _pending_placeholder_markdown(candidate: SkillDefinition) -> str:
    marker = hashlib.sha256(candidate.skill_id.encode()).hexdigest()[:12]
    return f"""---
id: {candidate.skill_id}
name: pending-{marker}
description: Internal inactive base for an encrypted offline review proposal
version: 0.0.0
category: {_PENDING_OFFLINE_CATEGORY}
parameters:
  topic:
    type: string
    description: Bounded evaluator input
    maxLength: 100
tools: []
---
# Workflow

Preserve the supplied input.
Do not add facts.
"""


def _is_pending_placeholder(definition: SkillDefinition) -> bool:
    return (
        definition.category == _PENDING_OFFLINE_CATEGORY
        and not definition.enabled
        and definition.version == "0.0.0"
        and definition.name.startswith("pending-")
    )


def _proposal_receipt(proposal: object) -> SkillEvolutionProposalReceipt:
    typed = cast("SkillEvolutionProposalRecordLike", proposal)
    return SkillEvolutionProposalReceipt(
        proposal_id=typed.id,
        base_revision=typed.base_revision,
        candidate_revision=typed.candidate_revision,
        candidate_digest=typed.candidate_content_hash,
        created_at=typed.created_at,
    )


class SkillEvolutionProposalRecordLike:
    id: uuid.UUID
    base_revision: int
    candidate_revision: int
    candidate_content_hash: str
    created_at: datetime

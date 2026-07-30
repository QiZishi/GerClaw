"""Tenant-scoped PostgreSQL persistence for custom Skills and session selections."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import (
    ConversationSession,
    SessionSkill,
    SkillDefinitionRecord,
    SkillDefinitionRevision,
    SkillEvolutionProposal,
    User,
)
from gerclaw_api.modules.skill.models import (
    SkillDefinition,
    SkillEvolutionDecision,
)
from gerclaw_api.modules.skill.storage_projection import (
    skill_content_hash,
    skill_name_fingerprint,
    skill_record_snapshot,
)


class SkillRepositoryConflictError(RuntimeError):
    """Raised for duplicate IDs or stale optimistic revisions."""


class SkillSessionNotFoundError(LookupError):
    """Raised when a session is not owned by the authenticated principal."""


class SqlAlchemySkillRepository:
    """Request-scoped repository that never accepts identity from Skill content."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_custom(self, *, tenant_id: str, actor_id: str) -> list[SkillDefinitionRecord]:
        result = await self._session.scalars(
            select(SkillDefinitionRecord)
            .where(
                SkillDefinitionRecord.tenant_id == tenant_id,
                SkillDefinitionRecord.actor_id == actor_id,
            )
            .order_by(SkillDefinitionRecord.updated_at.desc(), SkillDefinitionRecord.skill_id)
        )
        return list(result)

    async def get_custom(
        self,
        skill_id: str,
        *,
        tenant_id: str,
        actor_id: str,
        for_update: bool = False,
    ) -> SkillDefinitionRecord | None:
        statement = select(SkillDefinitionRecord).where(
            SkillDefinitionRecord.tenant_id == tenant_id,
            SkillDefinitionRecord.actor_id == actor_id,
            SkillDefinitionRecord.skill_id == skill_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(SkillDefinitionRecord | None, await self._session.scalar(statement))

    async def create_custom(
        self,
        definition: SkillDefinition,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> SkillDefinitionRecord:
        if (
            await self.get_custom(definition.skill_id, tenant_id=tenant_id, actor_id=actor_id)
            is not None
        ):
            raise SkillRepositoryConflictError("a Skill with this id already exists")
        record = SkillDefinitionRecord(
            tenant_id=tenant_id,
            actor_id=actor_id,
            skill_id=definition.skill_id,
            name=definition.name,
            name_fingerprint=skill_name_fingerprint(definition.name),
            description=definition.description,
            version=definition.version,
            category=definition.category,
            origin=definition.origin,
            tool_names=definition.tool_names,
            source_markdown=definition.source_markdown,
            content_hash=skill_content_hash(definition.source_markdown),
            enabled=definition.enabled,
            revision=1,
        )
        self._session.add(record)
        await self._flush_unique_conflict()
        return record

    async def update_custom(
        self,
        skill_id: str,
        *,
        tenant_id: str,
        actor_id: str,
        expected_revision: int,
        definition: SkillDefinition | None = None,
        enabled: bool | None = None,
    ) -> SkillDefinitionRecord | None:
        record = await self.get_custom(
            skill_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        if record is None:
            return None
        if record.revision != expected_revision:
            raise SkillRepositoryConflictError("Skill revision is stale")
        self._session.add(
            SkillDefinitionRevision(
                tenant_id=tenant_id,
                actor_id=actor_id,
                skill_definition_id=record.id,
                revision=record.revision,
                snapshot=skill_record_snapshot(record),
            )
        )
        if definition is not None:
            record.name = definition.name
            record.name_fingerprint = skill_name_fingerprint(definition.name)
            record.description = definition.description
            record.version = definition.version
            record.category = definition.category
            record.origin = definition.origin
            record.tool_names = definition.tool_names
            record.source_markdown = definition.source_markdown
            record.content_hash = skill_content_hash(definition.source_markdown)
        if enabled is not None:
            record.enabled = enabled
        record.revision += 1
        await self._flush_unique_conflict()
        # SQL expressions such as ``updated_at=now()`` are expired after UPDATE.
        # Refresh while still inside the async greenlet so response serialization
        # cannot trigger implicit synchronous I/O after commit.
        await self._session.refresh(record)
        return record

    async def create_evolution_proposal(
        self,
        skill_id: str,
        *,
        tenant_id: str,
        actor_id: str,
        expected_revision: int,
        current: SkillDefinition,
        candidate: SkillDefinition,
        decision: SkillEvolutionDecision,
        change_request: str,
        trace_id: str,
        request_fingerprint: str,
    ) -> SkillEvolutionProposal:
        """Persist one encrypted immutable candidate without activating it."""

        record = await self.get_custom(
            skill_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        if record is None:
            raise SkillRepositoryConflictError("Skill not found")
        if (
            record.revision != expected_revision
            or current.revision != expected_revision
            or candidate.revision != expected_revision + 1
            or record.content_hash != skill_content_hash(current.source_markdown)
        ):
            raise SkillRepositoryConflictError("Skill revision is stale")
        candidate_content_hash = skill_content_hash(candidate.source_markdown)
        existing = await self._session.scalar(
            select(SkillEvolutionProposal).where(
                SkillEvolutionProposal.tenant_id == tenant_id,
                SkillEvolutionProposal.actor_id == actor_id,
                SkillEvolutionProposal.skill_id == skill_id,
                SkillEvolutionProposal.base_revision == expected_revision,
                SkillEvolutionProposal.candidate_content_hash == candidate_content_hash,
            )
        )
        if existing is not None:
            return existing
        proposal = SkillEvolutionProposal(
            tenant_id=tenant_id,
            actor_id=actor_id,
            trace_id=trace_id,
            request_fingerprint=request_fingerprint,
            skill_record_id=record.id,
            skill_id=skill_id,
            base_revision=expected_revision,
            candidate_revision=candidate.revision,
            base_version=current.version,
            candidate_version=candidate.version,
            track=decision.track,
            object_kind=decision.object_kind,
            authority=decision.authority,
            review_state="pending_offline_review",
            reason_codes=list(decision.reason_codes),
            change_request=change_request,
            base_snapshot=current.model_dump(mode="json"),
            candidate_snapshot=candidate.model_dump(mode="json"),
            base_content_hash=record.content_hash,
            candidate_content_hash=candidate_content_hash,
        )
        self._session.add(proposal)
        await self._flush_unique_conflict()
        return proposal

    async def get_evolution_proposal(
        self,
        proposal_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> SkillEvolutionProposal | None:
        """Read a proposal only inside its exact owner scope."""

        return cast(
            SkillEvolutionProposal | None,
            await self._session.scalar(
                select(SkillEvolutionProposal).where(
                    SkillEvolutionProposal.id == proposal_id,
                    SkillEvolutionProposal.tenant_id == tenant_id,
                    SkillEvolutionProposal.actor_id == actor_id,
                )
            ),
        )

    async def delete_custom(
        self,
        skill_id: str,
        *,
        tenant_id: str,
        actor_id: str,
        expected_revision: int,
    ) -> bool:
        record = await self.get_custom(
            skill_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            for_update=True,
        )
        if record is None:
            return False
        if record.revision != expected_revision:
            raise SkillRepositoryConflictError("Skill revision is stale")
        await self._session.execute(
            delete(SessionSkill).where(
                SessionSkill.tenant_id == tenant_id,
                SessionSkill.actor_id == actor_id,
                SessionSkill.skill_id == skill_id,
            )
        )
        await self._session.delete(record)
        await self._session.flush()
        return True

    async def list_session_skills(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> list[str]:
        await self._assert_session_owner(session_id, tenant_id=tenant_id, actor_id=actor_id)
        result = await self._session.scalars(
            select(SessionSkill.skill_id)
            .where(
                SessionSkill.tenant_id == tenant_id,
                SessionSkill.actor_id == actor_id,
                SessionSkill.session_id == session_id,
            )
            .order_by(SessionSkill.position)
        )
        return list(result)

    async def replace_session_skills(
        self,
        session_id: uuid.UUID,
        skill_ids: list[str],
        *,
        tenant_id: str,
        actor_id: str,
    ) -> None:
        conversation = await self._assert_session_owner(
            session_id, tenant_id=tenant_id, actor_id=actor_id
        )
        if conversation.user_id is None:  # pragma: no cover - owner query requires an active user
            raise SkillSessionNotFoundError("session not found")
        await self._session.execute(
            delete(SessionSkill).where(
                SessionSkill.tenant_id == tenant_id,
                SessionSkill.actor_id == actor_id,
                SessionSkill.session_id == session_id,
            )
        )
        self._session.add_all(
            [
                SessionSkill(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    user_id=conversation.user_id,
                    session_id=session_id,
                    skill_id=skill_id,
                    position=position,
                )
                for position, skill_id in enumerate(skill_ids)
            ]
        )
        await self._session.flush()

    async def _assert_session_owner(
        self,
        session_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> ConversationSession:
        session = await self._session.scalar(
            select(ConversationSession)
            .join(User, User.id == ConversationSession.user_id)
            .where(
                ConversationSession.id == session_id,
                ConversationSession.tenant_id == tenant_id,
                ConversationSession.status == "active",
                User.tenant_id == tenant_id,
                User.external_id == actor_id,
                User.is_active.is_(True),
            )
        )
        if session is None:
            raise SkillSessionNotFoundError("session not found")
        return session

    async def commit(self) -> None:
        """Commit a standalone Skill mutation."""

        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise SkillRepositoryConflictError(
                    "a Skill uniqueness constraint failed"
                ) from error
            raise

    async def _flush_unique_conflict(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as error:
            await self._session.rollback()
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise SkillRepositoryConflictError(
                    "a Skill uniqueness constraint failed"
                ) from error
            raise

"""Operator-only append ledger for offline Skill proposal review."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import (
    SkillDefinitionRecord,
    SkillDefinitionRevision,
    SkillEvolutionProposal,
    SkillEvolutionReviewEvent,
)
from gerclaw_api.modules.skill.models import SkillDefinition
from gerclaw_api.modules.skill.offline_contracts import (
    TERMINAL_SKILL_REVIEW_EVENTS,
    SkillReviewEventAppend,
)
from gerclaw_api.modules.skill.storage_projection import (
    skill_content_hash,
    skill_name_fingerprint,
    skill_record_snapshot,
)


class SkillEvolutionControlConflictError(RuntimeError):
    """Raised when an append would violate immutable review history."""


class SkillEvolutionControlRepository:
    """Control-plane repository; intentionally absent from FastAPI dependencies."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_proposal_for_update(
        self,
        proposal_id: uuid.UUID,
    ) -> SkillEvolutionProposal | None:
        return cast(
            SkillEvolutionProposal | None,
            await self._session.scalar(
                select(SkillEvolutionProposal)
                .where(SkillEvolutionProposal.id == proposal_id)
                .with_for_update()
            ),
        )

    async def list_events(
        self,
        proposal_id: uuid.UUID,
    ) -> tuple[SkillEvolutionReviewEvent, ...]:
        values = await self._session.scalars(
            select(SkillEvolutionReviewEvent)
            .where(SkillEvolutionReviewEvent.proposal_id == proposal_id)
            .order_by(
                SkillEvolutionReviewEvent.sequence,
                SkillEvolutionReviewEvent.id,
            )
        )
        return tuple(values)

    async def get_skill_for_update(
        self,
        proposal: SkillEvolutionProposal,
    ) -> SkillDefinitionRecord | None:
        return cast(
            SkillDefinitionRecord | None,
            await self._session.scalar(
                select(SkillDefinitionRecord)
                .where(
                    SkillDefinitionRecord.id == proposal.skill_record_id,
                    SkillDefinitionRecord.tenant_id == proposal.tenant_id,
                    SkillDefinitionRecord.actor_id == proposal.actor_id,
                    SkillDefinitionRecord.skill_id == proposal.skill_id,
                )
                .with_for_update()
            ),
        )

    async def append_event(
        self,
        proposal_id: uuid.UUID,
        command: SkillReviewEventAppend,
    ) -> SkillEvolutionReviewEvent:
        proposal = await self.get_proposal_for_update(proposal_id)
        if proposal is None:
            raise SkillEvolutionControlConflictError("SKILL_PROPOSAL_NOT_FOUND")
        events = await self.list_events(proposal_id)
        if any(item.event_type in TERMINAL_SKILL_REVIEW_EVENTS for item in events):
            raise SkillEvolutionControlConflictError("SKILL_PROPOSAL_ALREADY_TERMINAL")
        if command.event_type == "activated" and not any(
            item.event_type == "approved" for item in events
        ):
            raise SkillEvolutionControlConflictError("SKILL_PROPOSAL_APPROVAL_MISSING")
        sequence = (
            await self._session.scalar(
                select(func.coalesce(func.max(SkillEvolutionReviewEvent.sequence), 0)).where(
                    SkillEvolutionReviewEvent.proposal_id == proposal_id
                )
            )
            or 0
        ) + 1
        event = SkillEvolutionReviewEvent(
            proposal_id=proposal_id,
            sequence=sequence,
            event_type=command.event_type,
            artifact_sha256=command.artifact_sha256,
            reason_codes=list(command.reason_codes),
            approval_ticket_digest=command.approval_ticket_digest,
        )
        self._session.add(event)
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise SkillEvolutionControlConflictError(
                "SKILL_PROPOSAL_REVIEW_APPEND_CONFLICT"
            ) from error
        return event

    async def apply_candidate(
        self,
        record: SkillDefinitionRecord,
        candidate: SkillDefinition,
    ) -> SkillDefinitionRecord:
        """Advance the locked record exactly once while retaining its prior revision."""

        self._session.add(
            SkillDefinitionRevision(
                tenant_id=record.tenant_id,
                actor_id=record.actor_id,
                skill_definition_id=record.id,
                revision=record.revision,
                snapshot=skill_record_snapshot(record),
            )
        )
        record.name = candidate.name
        record.name_fingerprint = skill_name_fingerprint(candidate.name)
        record.description = candidate.description
        record.version = candidate.version
        record.category = candidate.category
        record.origin = candidate.origin
        record.tool_names = candidate.tool_names
        record.source_markdown = candidate.source_markdown
        record.content_hash = skill_content_hash(candidate.source_markdown)
        record.enabled = candidate.enabled
        record.revision = candidate.revision
        await self._session.flush()
        await self._session.refresh(record)
        return record

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

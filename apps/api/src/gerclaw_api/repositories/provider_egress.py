"""PHI-free persistence for auditable external-provider egress decisions."""

from __future__ import annotations

import uuid
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import ProviderEgressEvent
from gerclaw_api.modules.privacy_redaction.models import RedactionResult


class SqlAlchemyProviderEgressRepository:
    """Stage only purpose, processor, policy version and category counts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_prepared(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        processor: Literal[
            "mimo_tts", "anysearch", "tavily", "model_primary", "model_backup1", "model_backup2"
        ],
        decisions: dict[Literal["text", "style"], RedactionResult],
    ) -> ProviderEgressEvent:
        primary = decisions.get("text")
        if primary is None or any(
            decision.purpose is not primary.purpose
            or decision.policy_version != primary.policy_version
            for decision in decisions.values()
        ):
            raise ValueError("provider egress decisions must share one purpose and policy version")
        event = ProviderEgressEvent(
            tenant_id=tenant_id,
            actor_id=actor_id,
            purpose=primary.purpose.value,
            processor=processor,
            policy_version=primary.policy_version,
            findings=[
                {"field": field, **finding.model_dump(mode="json")}
                for field, decision in decisions.items()
                for finding in decision.findings
            ],
            outcome="prepared",
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def record_prepared_model_prompt(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        processor: Literal["model_primary", "model_backup1", "model_backup2"],
        decision: RedactionResult,
    ) -> ProviderEgressEvent:
        """Record one model slot without storing provider identity or prompt text."""

        if decision.purpose.value != "external_model_prompt":
            raise ValueError("model prompt audit requires an external_model_prompt decision")
        return await self.record_prepared(
            tenant_id=tenant_id,
            actor_id=actor_id,
            processor=processor,
            decisions={"text": decision},
        )

    async def get_model_prompt_for_owner(
        self,
        event_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> ProviderEgressEvent | None:
        statement = (
            select(ProviderEgressEvent)
            .where(
                ProviderEgressEvent.id == event_id,
                ProviderEgressEvent.tenant_id == tenant_id,
                ProviderEgressEvent.actor_id == actor_id,
                ProviderEgressEvent.purpose == "external_model_prompt",
                ProviderEgressEvent.processor.in_(
                    ("model_primary", "model_backup1", "model_backup2")
                ),
            )
            .with_for_update()
        )
        return cast(ProviderEgressEvent | None, await self._session.scalar(statement))

    async def record_prepared_asr_audio(
        self, *, tenant_id: str, actor_id: str
    ) -> ProviderEgressEvent:
        """Record bounded audio egress without claiming text redaction or consent.

        Audio cannot safely pass through the text-redaction boundary. The empty
        findings list therefore means only that no text classification occurred;
        it must never be interpreted as an absence of PHI in the audio.
        """

        event = ProviderEgressEvent(
            tenant_id=tenant_id,
            actor_id=actor_id,
            purpose="external_asr_audio",
            processor="mimo_asr",
            policy_version="audio-egress-v1",
            findings=[],
            outcome="prepared",
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def record_prepared_document_parse(
        self, *, tenant_id: str, actor_id: str, capability_version: str
    ) -> ProviderEgressEvent:
        """Record one MinerU parse without persisting file metadata or content.

        The configured adapter capability is PHI-free operational provenance. It
        lets a bad case be tied to the exact MinerU contract without retaining a
        filename, byte count, Markdown or document identifier.
        """

        event = ProviderEgressEvent(
            tenant_id=tenant_id,
            actor_id=actor_id,
            purpose="external_document_parse",
            processor="mineru",
            policy_version="document-egress-v1",
            findings=[{"field": "capability_version", "value": capability_version}],
            outcome="prepared",
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def set_outcome(
        self, event: ProviderEgressEvent, *, outcome: Literal["succeeded", "failed"]
    ) -> None:
        event.outcome = outcome
        await self._session.flush()

    async def get_document_parse_for_owner(
        self, event_id: uuid.UUID, *, tenant_id: str, actor_id: str
    ) -> ProviderEgressEvent | None:
        statement = (
            select(ProviderEgressEvent)
            .where(
                ProviderEgressEvent.id == event_id,
                ProviderEgressEvent.tenant_id == tenant_id,
                ProviderEgressEvent.actor_id == actor_id,
                ProviderEgressEvent.purpose == "external_document_parse",
                ProviderEgressEvent.processor == "mineru",
            )
            .with_for_update()
        )
        return cast(ProviderEgressEvent | None, await self._session.scalar(statement))

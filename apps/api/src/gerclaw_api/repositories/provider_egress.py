"""PHI-free persistence for auditable external-provider egress decisions."""

from __future__ import annotations

from typing import Literal

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
        processor: Literal["mimo_tts", "anysearch", "tavily"],
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

    async def set_outcome(
        self, event: ProviderEgressEvent, *, outcome: Literal["succeeded", "failed"]
    ) -> None:
        event.outcome = outcome
        await self._session.flush()

"""Independent durable audit sink for provider-bound model prompts."""

from __future__ import annotations

import uuid
from typing import Literal

from gerclaw_api.database.session import Database
from gerclaw_api.modules.privacy_redaction.models import RedactionResult
from gerclaw_api.repositories.provider_egress import SqlAlchemyProviderEgressRepository


class SqlAlchemyModelPromptEgressAudit:
    """Commit PHI-free events outside a chat turn's atomic data transaction."""

    def __init__(self, database: Database, *, tenant_id: str, actor_id: str) -> None:
        self._database = database
        self._tenant_id = tenant_id
        self._actor_id = actor_id

    async def prepare(
        self,
        *,
        preference: Literal["primary", "backup1", "backup2"],
        decision: RedactionResult,
    ) -> object:
        processor = f"model_{preference}"
        async with self._database.session() as session:
            event = await SqlAlchemyProviderEgressRepository(session).record_prepared_model_prompt(
                tenant_id=self._tenant_id,
                actor_id=self._actor_id,
                processor=processor,  # type: ignore[arg-type]
                decision=decision,
            )
            await session.commit()
            return event.id

    async def finish(self, handle: object, *, outcome: Literal["succeeded", "failed"]) -> None:
        if not isinstance(handle, uuid.UUID):
            raise ValueError("model prompt audit handle is invalid")
        async with self._database.session() as session:
            repository = SqlAlchemyProviderEgressRepository(session)
            event = await repository.get_model_prompt_for_owner(
                handle, tenant_id=self._tenant_id, actor_id=self._actor_id
            )
            if event is None or event.outcome != "prepared":
                raise ValueError("model prompt audit event is unavailable")
            await repository.set_outcome(event, outcome=outcome)
            await session.commit()

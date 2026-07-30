"""Versioned answer registration and current-version selection."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from gerclaw_api.database.models import AgentRun, AnswerVersion, Message
from gerclaw_api.domain.run_schemas import (
    AnswerVersionRead,
    AnswerVersionRegister,
    AnswerVersionSelect,
)
from gerclaw_api.repositories.answer_version import AnswerVersionRepository
from gerclaw_api.services.message_content import (
    StoredMessageContentError,
    read_message_citations,
    read_message_text,
)


class AnswerVersionNotFoundError(LookupError):
    """Raised without revealing whether another principal owns a run or message."""


class AnswerVersionConflictError(RuntimeError):
    """Raised when current-version state changed since the caller read it."""


class AnswerVersionDataError(RuntimeError):
    """Raised when stored current pointers violate the version invariant."""


class AnswerVersionService:
    """Keep answer history immutable and change only the explicit current pointer."""

    def __init__(self, repository: AnswerVersionRepository) -> None:
        self._repository = repository

    async def register(
        self,
        run_id: uuid.UUID,
        request: AnswerVersionRegister,
        *,
        tenant_id: str,
        actor_id: str,
        commit: bool = True,
    ) -> AnswerVersionRead:
        run = await self._locked_run(run_id, tenant_id=tenant_id, actor_id=actor_id)
        message = await self._repository.get_assistant_message(
            request.assistant_message_id,
            tenant_id=tenant_id,
            conversation_id=run.conversation_id,
        )
        if message is None:
            await self._repository.rollback()
            raise AnswerVersionNotFoundError(str(request.assistant_message_id))
        await self._validate_message_projection(message)
        producer_run_id = request.producer_run_id or run.id
        producer_run = await self._repository.get_owned_producer_run(
            producer_run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=run.conversation_id,
        )
        if producer_run is None or message.trace_id != producer_run.trace_id:
            await self._repository.rollback()
            raise AnswerVersionNotFoundError(str(producer_run_id))
        existing = await self._repository.get_by_message(run.id, request.assistant_message_id)
        if existing is not None:
            result = self.to_public(existing, message)
            await self._repository.rollback()
            return result

        current = await self._repository.get_current(run.id)
        if not self._current_pointer_is_consistent(run, current):
            await self._repository.rollback()
            raise AnswerVersionDataError("run current answer pointer is inconsistent")
        if request.expected_current_version_id is not None and (
            current is None or current.id != request.expected_current_version_id
        ):
            await self._repository.rollback()
            raise AnswerVersionConflictError("current answer version changed")
        if current is None:
            answer_group_id = uuid.uuid4()
            version_number = 1
            supersedes_id = None
        else:
            answer_group_id = current.answer_group_id
            version_number = current.version + 1
            supersedes_id = current.id
            current.is_current = False
            await self._repository.flush()

        version = AnswerVersion(
            id=uuid.uuid4(),
            run_id=run.id,
            producer_run_id=producer_run.id,
            answer_group_id=answer_group_id,
            assistant_message_id=message.id,
            version=version_number,
            is_current=True,
            supersedes_id=supersedes_id,
            created_at=datetime.now(UTC),
        )
        try:
            await self._repository.add_version(version)
            # Insert the referenced version before moving the run's FK pointer.
            await self._repository.flush()
            run.current_answer_version_id = version.id
            if commit:
                await self._repository.commit()
            else:
                await self._repository.flush()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_public(version, message)

    async def list_versions(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        limit: int = 50,
    ) -> list[AnswerVersionRead]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        run = await self._locked_run(run_id, tenant_id=tenant_id, actor_id=actor_id)
        versions = await self._repository.list_versions(run.id, limit=limit)
        try:
            result: list[AnswerVersionRead] = []
            for version in versions:
                message = await self._message_for_version(
                    version,
                    run=run,
                    tenant_id=tenant_id,
                )
                result.append(self.to_public(version, message))
            return result
        finally:
            await self._repository.rollback()

    async def select(
        self,
        run_id: uuid.UUID,
        version_id: uuid.UUID,
        request: AnswerVersionSelect,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AnswerVersionRead:
        run = await self._locked_run(run_id, tenant_id=tenant_id, actor_id=actor_id)
        current = await self._repository.get_current(run.id)
        if not self._current_pointer_is_consistent(run, current):
            await self._repository.rollback()
            raise AnswerVersionDataError("run current answer pointer is inconsistent")
        if current is None:
            await self._repository.rollback()
            raise AnswerVersionNotFoundError(str(version_id))
        if current.id != request.expected_current_version_id:
            await self._repository.rollback()
            raise AnswerVersionConflictError("current answer version changed")
        target = await self._repository.get_version(run.id, version_id)
        if target is None:
            await self._repository.rollback()
            raise AnswerVersionNotFoundError(str(version_id))
        message = await self._message_for_version(
            target,
            run=run,
            tenant_id=tenant_id,
        )
        if message is None:
            await self._repository.rollback()
            raise AnswerVersionNotFoundError(str(version_id))
        await self._validate_message_projection(message)
        if target.id == current.id:
            result = self.to_public(target, message)
            await self._repository.rollback()
            return result

        try:
            current.is_current = False
            await self._repository.flush()
            target.is_current = True
            await self._repository.flush()
            run.current_answer_version_id = target.id
            await self._repository.commit()
        except BaseException:
            await self._repository.rollback()
            raise
        return self.to_public(target, message)

    async def _message_for_version(
        self,
        version: AnswerVersion,
        *,
        run: AgentRun,
        tenant_id: str,
    ) -> Message | None:
        if version.assistant_message_id is None:
            return None
        return await self._repository.get_assistant_message(
            version.assistant_message_id,
            tenant_id=tenant_id,
            conversation_id=run.conversation_id,
        )

    async def _validate_message_projection(self, message: Message) -> None:
        try:
            read_message_text(message)
            read_message_citations(message)
        except StoredMessageContentError as error:
            await self._repository.rollback()
            raise AnswerVersionDataError(str(error)) from error

    async def _locked_run(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRun:
        run = await self._repository.get_owned_run_for_update(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if run is None:
            raise AnswerVersionNotFoundError(str(run_id))
        return run

    @staticmethod
    def _current_pointer_is_consistent(
        run: AgentRun,
        current: AnswerVersion | None,
    ) -> bool:
        current_id = current.id if current is not None else None
        return run.current_answer_version_id == current_id

    @staticmethod
    def to_public(
        version: AnswerVersion,
        message: Message | None = None,
    ) -> AnswerVersionRead:
        try:
            answer_markdown = read_message_text(message) if message is not None else None
            citations = read_message_citations(message) if message is not None else ()
            return AnswerVersionRead(
                id=version.id,
                run_id=version.run_id,
                producer_run_id=version.producer_run_id,
                answer_group_id=version.answer_group_id,
                assistant_message_id=version.assistant_message_id,
                version=version.version,
                is_current=version.is_current,
                supersedes_id=version.supersedes_id,
                answer_markdown=answer_markdown,
                citations=citations,
                created_at=version.created_at,
            )
        except StoredMessageContentError as error:
            raise AnswerVersionDataError(str(error)) from error

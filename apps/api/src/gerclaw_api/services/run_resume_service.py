"""Validate and reconstruct an explicit retry for one interrupted Agent Run."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.domain.chat_schemas import ChatRequest
from gerclaw_api.domain.run_schemas import AgentRunRead, AgentRunStatus
from gerclaw_api.modules.agent_harness.context_snapshot import (
    FrozenRunState,
    PersistedContextSnapshot,
    PersistedRunPlan,
)
from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.modules.input_output import ImageInput
from gerclaw_api.repositories.run_resume import RunResumeRecord, RunResumeRepository
from gerclaw_api.services.agent_run_service import AgentRunService
from gerclaw_api.services.run_regeneration_service import image_fingerprint


class RunResumeNotFoundError(LookupError):
    """Raised without revealing another principal's Run."""


class RunResumeConflictError(RuntimeError):
    """Raised when a Run is not in the exact durable state required for resume."""


class RunResumeDataError(RuntimeError):
    """Raised when encrypted resume material fails its strict schema boundary."""


class _StoredTextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["text"]
    text: str = Field(min_length=1, max_length=50_000)


class _StoredImageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(pattern=r"^ev_img[a-f0-9]{24}$")
    media_type: Literal["image/jpeg", "image/png", "image/webp", "image/gif"]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=1, le=5 * 1024 * 1024)
    base64: str = Field(min_length=4, max_length=7_000_000)


@dataclass(frozen=True, slots=True)
class RunResumeCommand:
    run_id: uuid.UUID
    trace_id: str
    request_id: str
    request: ChatRequest
    state: FrozenRunState


class RunResumeService:
    def __init__(self, repository: RunResumeRepository) -> None:
        self._repository = repository

    async def latest_recoverable(
        self,
        conversation_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> AgentRunRead | None:
        run = await self._repository.get_latest_recoverable(
            conversation_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        result = AgentRunService.to_public_run(run) if run is not None else None
        await self._repository.rollback()
        return result

    async def prepare(
        self,
        run_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        controlled_directive_id: uuid.UUID | None = None,
    ) -> RunResumeCommand:
        record = await self._repository.get_owned_context(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if record is None:
            await self._repository.rollback()
            raise RunResumeNotFoundError(str(run_id))
        try:
            run_status = AgentRunStatus(record.run.status)
            RouteKind(record.run.route)
        except ValueError as error:
            await self._repository.rollback()
            raise RunResumeDataError("stored Run identity is invalid") from error
        if (
            run_status is not AgentRunStatus.INTERRUPTED
            or record.run.current_answer_version_id is not None
            or record.trace.status != "running"
        ):
            await self._repository.rollback()
            raise RunResumeConflictError("run is not safely resumable")
        controlled_successor_id = await self._repository.get_controlled_successor_id(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if controlled_successor_id is not None and controlled_directive_id is None:
            await self._repository.rollback()
            raise RunResumeConflictError(
                "run was replaced by a controlled successor"
            )
        active_steer_id = await self._repository.get_active_steer_directive_id(
            run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if (
            active_steer_id is not None
            and active_steer_id != controlled_directive_id
        ) or (
            controlled_directive_id is not None
            and active_steer_id != controlled_directive_id
        ):
            await self._repository.rollback()
            raise RunResumeConflictError(
                "run is reserved for a controlled successor"
            )
        if record.input_message.role != "user":
            await self._repository.rollback()
            raise RunResumeDataError("stored Run identity is invalid")
        persisted_run_id = record.run.id
        persisted_trace_id = record.run.trace_id
        try:
            text_blocks = [
                _StoredTextBlock.model_validate(item)
                for item in record.input_message.content
            ]
            message = "\n".join(block.text for block in text_blocks).strip()
            state = FrozenRunState(
                snapshot=PersistedContextSnapshot.model_validate(
                    record.run.context_snapshot
                ),
                plan=PersistedRunPlan.model_validate(record.run.plan),
            )
            self._validate_frozen_identity(
                state,
                record=record,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
            plan = state.plan
            if plan.channel != "web":
                raise ValueError("stored Run channel is not supported by chat resume")
            images = self._restore_images(
                record.trace.private_input_artifacts,
                plan=plan,
            )
            request = ChatRequest(
                session_id=record.run.conversation_id,
                message=message,
                loaded_skills=list(plan.loaded_skill_ids),
                requested_capabilities=list(plan.requested_capability_ids),
                uploaded_files=list(plan.uploaded_document_ids),
                images=images,
                channel="web",
                workflow=plan.workflow,
                regenerate_from_run_id=plan.regenerate_from_run_id,
                expected_current_answer_version_id=(
                    plan.expected_current_answer_version_id
                ),
            )
        except (TypeError, ValueError) as error:
            await self._repository.rollback()
            raise RunResumeDataError("stored Run resume material is invalid") from error
        await self._repository.rollback()
        return RunResumeCommand(
            run_id=persisted_run_id,
            trace_id=persisted_trace_id,
            request_id=state.snapshot.agent_context.execution.request_id,
            request=request,
            state=state,
        )

    @staticmethod
    def _validate_frozen_identity(
        state: FrozenRunState,
        *,
        record: RunResumeRecord,
        tenant_id: str,
        actor_id: str,
    ) -> None:
        execution = state.snapshot.agent_context.execution
        if (
            state.snapshot.input_message_id != record.run.input_message_id
            or execution.tenant_id != tenant_id
            or execution.actor_id != actor_id
            or execution.session_id != record.run.conversation_id
            or execution.trace_id != record.run.trace_id
            or execution.request_id != record.trace.request_id
            or state.plan.route_decision.route.value != record.run.route
        ):
            raise ValueError("stored snapshot identity does not match its Run")

    @staticmethod
    def _restore_images(
        artifacts: dict[str, object] | None,
        *,
        plan: PersistedRunPlan,
    ) -> list[ImageInput]:
        if plan.uploaded_image_count == 0:
            return []
        raw_images = (artifacts or {}).get("images")
        if not isinstance(raw_images, list) or len(raw_images) != plan.uploaded_image_count:
            raise ValueError("stored image count does not match resume plan")
        images: list[ImageInput] = []
        for raw_image, expected_fingerprint in zip(
            raw_images,
            plan.uploaded_image_fingerprints,
            strict=True,
        ):
            stored = _StoredImageRecord.model_validate(raw_image)
            image = ImageInput(media_type=stored.media_type, base64=stored.base64)
            if (
                image.sha256 != stored.sha256
                or image.evidence_id != stored.evidence_id
                or image.size_bytes != stored.size_bytes
                or image_fingerprint(image.media_type, image.base64)
                != expected_fingerprint
            ):
                raise ValueError("stored image integrity validation failed")
            images.append(image)
        return images

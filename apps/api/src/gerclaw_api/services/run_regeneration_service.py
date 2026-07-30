"""Fail-closed validation for server-side answer regeneration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gerclaw_api.domain.chat_schemas import ChatRequest
from gerclaw_api.domain.run_schemas import (
    AgentRunStatus,
    RunRegenerationContext,
)
from gerclaw_api.repositories.run_regeneration import RunRegenerationRepository


class RunRegenerationNotFoundError(LookupError):
    """Raised without revealing another principal's Run."""


class RunRegenerationConflictError(RuntimeError):
    """Raised when the requested replacement no longer matches durable facts."""


class _StoredTextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    text: str = Field(min_length=1, max_length=4_000)


def image_fingerprint(media_type: str, base64_payload: str) -> str:
    canonical = json.dumps(
        {"media_type": media_type, "base64": base64_payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class RunRegenerationService:
    """Accept regeneration only for the current answer and exact original input."""

    def __init__(self, repository: RunRegenerationRepository) -> None:
        self._repository = repository

    async def resolve(
        self,
        request: ChatRequest,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> RunRegenerationContext | None:
        source_run_id = request.regenerate_from_run_id
        expected_version_id = request.expected_current_answer_version_id
        if source_run_id is None or expected_version_id is None:
            return None
        source = await self._repository.get_owned_source(
            source_run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if source is None:
            await self._repository.rollback()
            raise RunRegenerationNotFoundError(str(source_run_id))
        try:
            run = source.run
            if AgentRunStatus(run.status) not in {
                AgentRunStatus.COMPLETED,
                AgentRunStatus.COMPLETED_WITH_WARNINGS,
            }:
                raise RunRegenerationConflictError("only completed runs can be regenerated")
            if (
                source.current_version is None
                or source.current_version.id != expected_version_id
                or run.current_answer_version_id != expected_version_id
            ):
                raise RunRegenerationConflictError("current answer version changed")
            if run.conversation_id != request.session_id:
                raise RunRegenerationConflictError("regeneration conversation changed")
            self._validate_input(source.input_message.content, request.message)
            self._validate_plan(run.plan, request)
            return RunRegenerationContext(
                source_run_id=run.id,
                source_trace_id=run.trace_id,
                input_message_id=run.input_message_id,
                current_answer_version_id=source.current_version.id,
            )
        finally:
            await self._repository.rollback()

    @staticmethod
    def _validate_input(raw_content: list[dict[str, Any]], request_text: str) -> None:
        try:
            blocks = [_StoredTextBlock.model_validate(item) for item in raw_content]
        except (ValidationError, TypeError) as error:
            raise RunRegenerationConflictError("stored regeneration input is invalid") from error
        stored = "\n".join(block.text for block in blocks if block.type == "text").strip()
        if not stored or stored != request_text:
            raise RunRegenerationConflictError("regeneration input changed")

    @staticmethod
    def _validate_plan(plan: dict[str, Any], request: ChatRequest) -> None:
        expected_workflow = plan.get("workflow")
        expected_skills = plan.get("loaded_skill_ids")
        expected_capabilities = plan.get("requested_capability_ids", [])
        expected_documents = plan.get("uploaded_document_ids")
        expected_images = plan.get("uploaded_image_fingerprints")
        if expected_skills is None and plan.get("loaded_skill_count") == 0:
            expected_skills = []
        if expected_documents is None and plan.get("uploaded_document_count") == 0:
            expected_documents = []
        if expected_images is None and plan.get("uploaded_image_count") == 0:
            expected_images = []
        actual_images = [
            image_fingerprint(image.media_type, image.base64) for image in request.images
        ]
        if (
            expected_workflow != request.workflow.value
            or expected_skills != [str(item) for item in request.loaded_skills]
            or expected_capabilities != request.requested_capabilities
            or expected_documents != [str(item) for item in request.uploaded_files]
            or expected_images != actual_images
        ):
            raise RunRegenerationConflictError("regeneration context changed")

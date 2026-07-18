"""Transactional chat turn orchestration across lease, Trace, Harness, and storage."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from gerclaw_api.auth import AuthContext
from gerclaw_api.config import Settings
from gerclaw_api.domain.chat_schemas import ChatDoneData, ChatRequest
from gerclaw_api.domain.enums import TraceEventStatus, TraceEventType, TraceStatus
from gerclaw_api.domain.trace_schemas import (
    TraceEventCreate,
    TraceFinishRequest,
    TraceStartRequest,
    bounded_trace_duration_ms,
)
from gerclaw_api.modules.agent_harness import (
    ConversationHistoryMessage,
    ProductionAgentHarness,
    StreamEvent,
    UnsupportedAgentContextError,
)
from gerclaw_api.modules.companion.policy import is_companion_workflow
from gerclaw_api.modules.contracts import AgentRequest, AgentResponse, ExecutionContext
from gerclaw_api.modules.document import DocumentService
from gerclaw_api.modules.input_output import ProductionInputOutputModule
from gerclaw_api.modules.memory.memory_module import ProductionMemoryModule
from gerclaw_api.modules.memory.models import MemoryUpdateResult
from gerclaw_api.modules.orchestration import (
    ChatCancellationFinalizationError,
    ChatReplayUnavailableError,
    ChatTurnCoordinator,
)
from gerclaw_api.modules.rag import HybridRAGModule
from gerclaw_api.modules.risk_alert.service import RiskAlertService
from gerclaw_api.modules.runtime.models import (
    ActorRole,
    ApprovalCreate,
    ApprovalRead,
    RuntimePrincipal,
)
from gerclaw_api.modules.search.protocols import SearchModule
from gerclaw_api.modules.skill.skill_module import ProductionSkillModule
from gerclaw_api.modules.workflows import get_default_workflow_registry
from gerclaw_api.repositories.approval import SqlAlchemyApprovalRepository
from gerclaw_api.security import JsonValue, audit_hmac_digest
from gerclaw_api.services.conversation_service import ConversationService
from gerclaw_api.services.model_router import FailoverChatModel
from gerclaw_api.services.session_lease import SessionLease, SessionLeaseGuard
from gerclaw_api.services.trace_service import TraceService

StreamCallback = Callable[[StreamEvent], Awaitable[None]]
CancellationProbe = Callable[[], Awaitable[bool]]
ActiveSkillCall = tuple[float, str, str | None]

__all__ = [
    "ChatCancellationFinalizationError",
    "ChatReplayUnavailableError",
    "ChatService",
]


class MemoryModuleFactory(Protocol):
    """Build a principal- and turn-isolated Memory graph."""

    def __call__(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        trace_id: str,
    ) -> ProductionMemoryModule: ...


def _fingerprint(payload: ChatRequest, settings: Settings) -> str:
    """Return a keyed payload identity without exposing enumerable user text."""

    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    key = settings.auth_jwt_secret.get_secret_value().encode()
    return audit_hmac_digest(key, canonical.encode())


def _event_id() -> str:
    return f"event_{uuid.uuid4().hex}"


def _finish_id() -> str:
    return f"finish_{uuid.uuid4().hex}"


def _runtime_principal(identity: AuthContext, *, user_id: uuid.UUID | None) -> RuntimePrincipal:
    """Project a verified API identity without inventing clinician authority.

    A patient proof is limited to the caller's own conversation subject. A
    doctor account remains a doctor identity, but receives no patient proof
    until the separately governed patient-authorisation flow exists.
    """

    role = ActorRole(identity.role)
    owns_patient_subject = role in {ActorRole.GUEST, ActorRole.PATIENT} and user_id is not None
    return RuntimePrincipal(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        role=role,
        scopes=identity.scopes,
        user_id=user_id,
        patient_id=user_id if owns_patient_subject else None,
        patient_access_verified=owns_patient_subject,
    )


class ChatService:
    """Execute one idempotent Agent turn and emit success only after commit."""

    def __init__(
        self,
        *,
        settings: Settings,
        conversation: ConversationService,
        traces: TraceService,
        lease: SessionLease,
        model: FailoverChatModel,
        rag_module: HybridRAGModule,
        memory_factory: MemoryModuleFactory,
        search_module: SearchModule | None = None,
        skill_module: ProductionSkillModule | None = None,
        approval_repository: SqlAlchemyApprovalRepository | None = None,
        document_service: DocumentService | None = None,
        risk_alert_service: RiskAlertService | None = None,
        input_output: ProductionInputOutputModule | None = None,
    ) -> None:
        self._settings = settings
        self._conversation = conversation
        self._traces = traces
        self._lease = lease
        self._model = model
        self._rag_module = rag_module
        self._memory_factory = memory_factory
        self._search_module = search_module
        self._skill_module = skill_module
        self._approval_repository = approval_repository
        self._document_service = document_service
        self._risk_alert_service = risk_alert_service
        self._input_output = input_output or ProductionInputOutputModule()

    async def process(
        self,
        payload: ChatRequest,
        *,
        identity: AuthContext,
        request_id: str,
        trace_id: str,
        callback: StreamCallback,
        cancellation_requested: CancellationProbe | None = None,
    ) -> AgentResponse:
        workflow = get_default_workflow_registry().validate_context(
            payload.workflow,
            loaded_skill_count=len(payload.loaded_skills),
            uploaded_file_count=len(payload.uploaded_files),
            uploaded_image_count=len(payload.images),
        )
        normalized = await self._input_output.normalize(
            AgentRequest(
                context=ExecutionContext(
                    request_id=request_id,
                    trace_id=trace_id,
                    tenant_id=identity.tenant_id,
                    actor_id=identity.actor_id,
                    session_id=payload.session_id,
                ),
                text=payload.message,
                channel=payload.channel,
            )
        )
        payload = payload.model_copy(update={"message": normalized.text})
        request_fingerprint = _fingerprint(payload, self._settings)
        active_skill_calls: dict[str, ActiveSkillCall] = {}
        skill_audit_events: list[TraceEventCreate] = []

        async def read_replay() -> AgentResponse | None:
            stored = await self._conversation.get_replayed_assistant(
                tenant_id=identity.tenant_id,
                trace_id=trace_id,
                session_id=payload.session_id,
            )
            return self._conversation.to_agent_response(stored) if stored is not None else None

        async def emit_replay(response: AgentResponse) -> None:
            await self._emit_replay(
                response,
                trace_id=trace_id,
                session_id=payload.session_id,
                callback=callback,
            )

        async def run_owned_turn(lease_guard: SessionLeaseGuard) -> AgentResponse:
            return await self._process_owned_turn(
                payload,
                identity=identity,
                request_id=request_id,
                trace_id=trace_id,
                request_fingerprint=request_fingerprint,
                lease_guard=lease_guard,
                callback=callback,
                cancellation_requested=cancellation_requested,
                active_skill_calls=active_skill_calls,
                skill_audit_events=skill_audit_events,
            )

        async def finalize_failure(
            status: TraceStatus,
            code: str,
            fencing_token: int | None,
            lease_guard: SessionLeaseGuard | None,
        ) -> bool:
            return await self._finish_failure(
                payload,
                identity=identity,
                trace_id=trace_id,
                status=status,
                code=code,
                request_fingerprint=request_fingerprint,
                fencing_token=fencing_token,
                lease_guard=lease_guard,
                active_skill_calls=active_skill_calls,
                skill_audit_events=skill_audit_events,
            )

        coordinator = ChatTurnCoordinator(
            conversation=self._conversation,
            traces=self._traces,
            lease=self._lease,
        )
        return await coordinator.execute(
            start_request=TraceStartRequest(
                session_id=payload.session_id,
                execution_type="agent.chat",
                attributes={
                    "channel": payload.channel,
                    "feature": "medical_chat",
                    "module": "agent_harness",
                    "operation": "process_message",
                    "request_fingerprint": request_fingerprint,
                    "workflow": workflow.workflow_id.value,
                    "workflow_version": workflow.version,
                    "workflow_owner_module": workflow.owner_module,
                },
            ),
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            session_id=payload.session_id,
            private_input_artifacts=(
                {"images": [image.trace_record() for image in payload.images]}
                if payload.images
                else None
            ),
            read_replay=read_replay,
            emit_replay=emit_replay,
            run_owned_turn=run_owned_turn,
            finalize_failure=finalize_failure,
            error_code=self.error_code,
            cancellation_requested=cancellation_requested,
        )

    async def _process_owned_turn(
        self,
        payload: ChatRequest,
        *,
        identity: AuthContext,
        request_id: str,
        trace_id: str,
        request_fingerprint: str,
        lease_guard: SessionLeaseGuard,
        callback: StreamCallback,
        cancellation_requested: CancellationProbe | None,
        active_skill_calls: dict[str, ActiveSkillCall],
        skill_audit_events: list[TraceEventCreate],
    ) -> AgentResponse:
        conversation = await self._conversation.ensure_session(
            payload.session_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
        )
        conversation = await self._conversation.claim_fencing_token(
            payload.session_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            fencing_token=lease_guard.fencing_token,
            trace_id=trace_id,
        )
        if conversation.user_id is None:
            raise RuntimeError("conversation has no active user principal")
        if payload.loaded_skills and self._skill_module is None:
            raise UnsupportedAgentContextError("Skill module is unavailable")
        agent_skills = (
            await self._skill_module.resolve_agent_skills(payload.loaded_skills)
            if self._skill_module is not None
            else []
        )
        skill_versions = {
            skill_id: version
            for skill in agent_skills
            if skill.dir.startswith("skill://") and "@" in skill.dir
            for skill_id, version in [skill.dir.removeprefix("skill://").rsplit("@", maxsplit=1)]
        }
        fallback_skill_id = (
            payload.loaded_skills[0] if len(payload.loaded_skills) == 1 else "unknown_skill"
        )
        fallback_skill_version = skill_versions.get(fallback_skill_id)
        if self._skill_module is not None:
            await self._skill_module.replace_session_skills(
                payload.session_id, payload.loaded_skills, commit=False
            )
        memory = self._memory_factory(
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            user_id=conversation.user_id,
            session_id=payload.session_id,
            trace_id=trace_id,
        )
        workflow = get_default_workflow_registry().validate_context(
            payload.workflow,
            loaded_skill_count=len(payload.loaded_skills),
            uploaded_file_count=len(payload.uploaded_files),
            uploaded_image_count=len(payload.images),
        )
        companion = is_companion_workflow(cast(Any, workflow.workflow_id.value))
        if companion:
            history = await self._conversation.load_history(
                payload.session_id,
                tenant_id=identity.tenant_id,
                actor_id=identity.actor_id,
                limit=self._settings.agent_history_messages,
            )
            session_summary = ""
            profile_context = ""
            profile_version = 0
            memory_refs: list[str] = []
        else:
            short_term = await memory.get_short_term(
                str(payload.session_id),
                max_turns=max(1, self._settings.agent_history_messages // 2),
            )
            compressed = await memory.compress_context(
                short_term,
                max_tokens=max(
                    1,
                    int(self._model.context_size * self._settings.memory_context_budget_ratio),
                ),
            )
            history = [
                ConversationHistoryMessage(role=message.role, text=message.text())
                for message in compressed
                if message.role in {"user", "assistant"} and message.text()
            ]
            session_summary = "\n\n".join(
                message.text()
                for message in compressed
                if message.role == "system" and message.text()
            )
            profile_context, profile_version, memory_refs = await memory.core_profile_context()
        await self._conversation.store_user_message(
            tenant_id=identity.tenant_id,
            conversation=conversation,
            session_id=payload.session_id,
            trace_id=trace_id,
            text=payload.message,
            channel=payload.channel,
        )
        if payload.uploaded_files and self._document_service is None:
            raise UnsupportedAgentContextError("uploaded document storage is unavailable")
        uploaded_documents = (
            await self._document_service.resolve_context(
                payload.uploaded_files,
                tenant_id=identity.tenant_id,
                actor_id=identity.actor_id,
                session_id=payload.session_id,
                max_characters=self._settings.document_context_max_characters,
            )
            if self._document_service is not None
            else []
        )
        execution = ExecutionContext(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            session_id=payload.session_id,
        )

        async def persist_approval(command: ApprovalCreate) -> ApprovalRead:
            if self._approval_repository is None:
                raise UnsupportedAgentContextError("Runtime approval storage is unavailable")
            record = await self._approval_repository.create(
                command,
                tenant_id=identity.tenant_id,
                requester_actor_id=identity.actor_id,
            )
            approval = ApprovalRead.model_validate(record)
            # This commit intentionally precedes the parked-turn exception. A
            # subsequent failure Trace must never erase an approval the user
            # has already been told to act on.
            await self._approval_repository.commit()
            return approval

        harness = ProductionAgentHarness(
            settings=self._settings,
            model=self._model,
            rag_module=self._rag_module,
            memory_module=memory,
            execution=execution,
            history=history,
            profile_context=profile_context,
            profile_version=profile_version,
            memory_refs=memory_refs,
            session_summary=session_summary,
            search_module=self._search_module,
            search_enabled=workflow.search_enabled,
            workflow=cast(Any, workflow.workflow_id.value),
            agent_skills=agent_skills,
            loaded_skill_ids=payload.loaded_skills,
            uploaded_documents=uploaded_documents,
            uploaded_images=payload.images,
            runtime_principal=_runtime_principal(identity, user_id=conversation.user_id),
            approval_callback=persist_approval,
        )
        context = await harness.assemble_context(
            str(payload.session_id),
            identity.actor_id,
            payload.loaded_skills,
            [str(item) for item in payload.uploaded_files],
        )
        await self._append_event(
            identity.tenant_id,
            trace_id,
            TraceEventType.AGENT_START,
            TraceEventStatus.STARTED,
            {
                "channel": payload.channel,
                "feature": "medical_chat",
                "module": "agent_harness",
                "operation": "process_message",
                "workflow": workflow.workflow_id.value,
                "workflow_version": workflow.version,
                "workflow_owner_module": workflow.owner_module,
            },
            commit=False,
        )

        async def projected(event: StreamEvent) -> None:
            if event.event_type == "done":
                return
            if event.event_type == "approval_required":
                approval_id = event.data.get("approval_id")
                tool_name = event.data.get("tool_name")
                status = event.data.get("status")
                policy_version = event.data.get("policy_version")
                tool_version = event.data.get("tool_version")
                expires_at = event.data.get("expires_at")
                if all(
                    isinstance(value, str)
                    for value in (
                        approval_id,
                        tool_name,
                        status,
                        policy_version,
                        tool_version,
                        expires_at,
                    )
                ):
                    await self._append_event(
                        identity.tenant_id,
                        trace_id,
                        TraceEventType.APPROVAL,
                        TraceEventStatus.STARTED,
                        {
                            "approval_id": approval_id,
                            "tool_name": tool_name,
                            "tool_version": tool_version,
                            "policy_version": policy_version,
                            "outcome": status,
                            "expires_at": expires_at,
                            "success": True,
                        },
                        # The harness immediately ends a parked turn. Persist
                        # the PHI-free audit record before that exception rolls
                        # back the normal turn unit of work.
                        commit=True,
                    )
            if event.event_type == "tool_call" and event.data.get("tool_name") == "Skill":
                tool_call_id = event.data.get("tool_call_id")
                if isinstance(tool_call_id, str):
                    active_skill_calls[tool_call_id] = (
                        time.monotonic(),
                        fallback_skill_id,
                        fallback_skill_version,
                    )
            if event.event_type == "tool_result":
                data = event.data
                result_status = data.get("status")
                success = result_status == "success"
                trace_status = (
                    TraceEventStatus.SUCCEEDED
                    if success
                    else TraceEventStatus.CANCELLED
                    if result_status == "cancelled"
                    else TraceEventStatus.FAILED
                )
                outcome = (
                    "success"
                    if success
                    else "cancelled"
                    if result_status == "cancelled"
                    else "failed"
                )
                raw_duration = data.get("duration_ms")
                duration_ms = (
                    raw_duration
                    if isinstance(raw_duration, int) and not isinstance(raw_duration, bool)
                    else 0
                )
                tool_name = data.get("tool_name", "unknown_tool")
                is_skill = tool_name == "Skill"
                tool_call_id = data.get("tool_call_id")
                pending_skill = (
                    active_skill_calls.pop(tool_call_id, None)
                    if isinstance(tool_call_id, str)
                    else None
                )
                skill_id = data.get("skill")
                skill_version = data.get("version")
                if is_skill:
                    resolved_skill = (
                        skill_id
                        if isinstance(skill_id, str)
                        else pending_skill[1]
                        if pending_skill is not None
                        else "unknown_skill"
                    )
                    resolved_version = (
                        skill_version
                        if isinstance(skill_version, str)
                        else pending_skill[2]
                        if pending_skill is not None
                        else None
                    )
                    audit_event = TraceEventCreate(
                        event_id=_event_id(),
                        event_type=TraceEventType.SKILL_EXECUTE,
                        status=trace_status,
                        payload={
                            "duration_ms": duration_ms,
                            "operation": "viewer",
                            "outcome": outcome,
                            "skill": resolved_skill,
                            "success": success,
                            **({"version": resolved_version} if resolved_version else {}),
                        },
                        duration_ms=duration_ms,
                    )
                    skill_audit_events.append(audit_event)
                    await self._traces.append_event(
                        identity.tenant_id,
                        trace_id,
                        audit_event,
                        commit=False,
                    )
                else:
                    await self._append_event(
                        identity.tenant_id,
                        trace_id,
                        TraceEventType.TOOL_CALL,
                        trace_status,
                        {
                            "duration_ms": duration_ms,
                            "operation": "execute",
                            "outcome": outcome,
                            "success": success,
                            "tool_name": tool_name,
                        },
                        duration_ms=duration_ms,
                        commit=False,
                    )
            await callback(event)

        try:
            response = await harness.process_message(
                payload.message,
                str(payload.session_id),
                context,
                projected,
            )
            # AgentScope middleware performs asynchronous cleanup when a model
            # stream is interrupted. A provider can finish during that cleanup
            # and consume the task cancellation. The durable intent is therefore
            # the final fence before an assistant response becomes replayable.
            if cancellation_requested is not None and await cancellation_requested():
                raise asyncio.CancelledError("explicit chat cancellation requested")
            # Conversation and Trace repositories share this request's
            # AsyncSession. Stage the assistant plus success events, then let the
            # terminal Trace transition commit the whole success unit atomically.
            await lease_guard.assert_owned()
            if response.emergency_short_circuit and self._risk_alert_service is not None:
                source_fingerprint = audit_hmac_digest(
                    self._settings.auth_jwt_secret.get_secret_value().encode(),
                    f"risk-alert:v1:chat:{trace_id}".encode(),
                )
                await self._risk_alert_service.sync_chat_red_flag(
                    tenant_id=identity.tenant_id,
                    actor_id=identity.actor_id,
                    source_fingerprint=source_fingerprint,
                )
            conversation = await self._conversation.assert_fencing_token(
                payload.session_id,
                tenant_id=identity.tenant_id,
                actor_id=identity.actor_id,
                fencing_token=lease_guard.fencing_token,
                trace_id=trace_id,
            )
            await self._conversation.store_assistant_message(
                tenant_id=identity.tenant_id,
                session=conversation,
                trace_id=trace_id,
                response=response,
                commit=False,
            )
            await self._record_success(
                identity.tenant_id,
                trace_id,
                response,
                memory_update=None if companion else memory.last_update,
                commit=False,
            )
            await self._traces.finish_trace(
                identity.tenant_id,
                trace_id,
                TraceFinishRequest(
                    idempotency_key=_finish_id(),
                    status=TraceStatus.COMPLETED,
                    attributes={
                        "outcome": "completed",
                        "request_fingerprint": request_fingerprint,
                        "success": True,
                    },
                ),
            )
        except BaseException:
            # Never leave a replayable assistant paired with a non-completed
            # Trace. The outer failure path records the durable failure after the
            # shared transaction has been cleared.
            try:
                await self._conversation.rollback()
            finally:
                await memory.compensate_uncommitted_vectors()
            raise
        if not companion:
            memory.mark_vectors_committed()
        rendered = await self._input_output.render(response, "web")
        done = ChatDoneData(
            full_text=rendered["text"],
            references=rendered["citations"],
            safety=rendered["safety"],
            trace_id=trace_id,
            session_id=payload.session_id,
        )
        await callback(
            StreamEvent(
                event_type="done",
                data=done.model_dump(mode="json"),
                timestamp=datetime.now(UTC),
            )
        )
        return response

    async def _record_success(
        self,
        tenant_id: str,
        trace_id: str,
        response: AgentResponse,
        *,
        memory_update: MemoryUpdateResult | None,
        commit: bool = True,
    ) -> None:
        structured = response.structured
        selected = structured.get("model_preference")
        model_invoked = structured.get("model_invoked") is True
        model_slot = selected if model_invoked and isinstance(selected, str) else "not_invoked"
        input_tokens = structured.get("input_tokens")
        output_tokens = structured.get("output_tokens")
        input_tokens = input_tokens if isinstance(input_tokens, int) else 0
        output_tokens = output_tokens if isinstance(output_tokens, int) else 0
        retry_count = structured.get("model_failures")
        retry_count = retry_count if isinstance(retry_count, int) else 0
        raw_search_attempts = structured.get("search_attempts")
        search_attempts = raw_search_attempts if isinstance(raw_search_attempts, list) else []
        for raw_attempt in search_attempts:
            if not isinstance(raw_attempt, dict):
                continue
            provider = raw_attempt.get("provider")
            outcome = raw_attempt.get("outcome")
            operation = raw_attempt.get("operation")
            retry_index = raw_attempt.get("retry_index")
            result_count = raw_attempt.get("result_count")
            duration_ms = raw_attempt.get("duration_ms")
            if not (
                isinstance(provider, str)
                and isinstance(outcome, str)
                and isinstance(operation, str)
                and isinstance(retry_index, int)
                and isinstance(result_count, int)
                and isinstance(duration_ms, int)
            ):
                continue
            attempt_success = outcome in {"success", "empty"}
            await self._append_event(
                tenant_id,
                trace_id,
                TraceEventType.SEARCH_QUERY,
                TraceEventStatus.SUCCEEDED if attempt_success else TraceEventStatus.FAILED,
                {
                    "duration_ms": duration_ms,
                    "operation": operation,
                    "outcome": outcome,
                    "provider": provider,
                    "result_count": result_count,
                    "retry_index": retry_index,
                    "success": attempt_success,
                },
                duration_ms=duration_ms,
                commit=commit,
            )
        if model_invoked:
            await self._append_event(
                tenant_id,
                trace_id,
                TraceEventType.MODEL_CALL,
                TraceEventStatus.SUCCEEDED,
                {
                    "input_tokens": input_tokens,
                    "model": model_slot,
                    "outcome": "success",
                    "output_tokens": output_tokens,
                    "retry_count": retry_count,
                    "success": True,
                    "total_tokens": input_tokens + output_tokens,
                },
                commit=commit,
            )
        if response.citations:
            citation_ids: list[JsonValue] = [item.source_id for item in response.citations]
            await self._append_event(
                tenant_id,
                trace_id,
                TraceEventType.RAG_RETRIEVE,
                TraceEventStatus.SUCCEEDED,
                {
                    "chunk_ids": citation_ids,
                    "citation_ids": citation_ids,
                    "document_count": len({item.title for item in response.citations}),
                    "operation": "agentic_evidence",
                    "success": True,
                },
                commit=commit,
            )
        if memory_update is not None:
            memory_ids: list[JsonValue] = [str(item) for item in memory_update.changed_fact_ids]
            memory_categories: list[JsonValue] = list(memory_update.categories)
            memory_changed = bool(memory_ids)
            await self._append_event(
                tenant_id,
                trace_id,
                TraceEventType.MEMORY_UPDATE,
                TraceEventStatus.SUCCEEDED if memory_changed else TraceEventStatus.SKIPPED,
                {
                    "categories": memory_categories,
                    "confirmed_count": memory_update.confirmed_count,
                    "event_count": len(memory_ids),
                    "inactive_count": memory_update.inactive_count,
                    "memory_ids": memory_ids,
                    "outcome": "updated" if memory_changed else "unchanged",
                    "pending_count": memory_update.pending_count,
                    "success": True,
                    "version": memory_update.profile_version,
                },
                commit=commit,
            )
        safety_flags: list[JsonValue] = list(response.safety.notices)
        await self._append_event(
            tenant_id,
            trace_id,
            TraceEventType.SAFETY_CHECK,
            TraceEventStatus.SUCCEEDED,
            {"outcome": "safe", "safety_flags": safety_flags, "success": True},
            commit=commit,
        )
        await self._append_event(
            tenant_id,
            trace_id,
            TraceEventType.AGENT_FINISH,
            TraceEventStatus.SUCCEEDED,
            {
                "citation_count": len(response.citations),
                "outcome": "completed",
                "safety_flags": safety_flags,
                "success": True,
                **(
                    {
                        "input_tokens": input_tokens,
                        "model": model_slot,
                        "output_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    }
                    if model_invoked
                    else {}
                ),
            },
            commit=commit,
        )

    async def _append_event(
        self,
        tenant_id: str,
        trace_id: str,
        event_type: TraceEventType,
        status: TraceEventStatus,
        payload: dict[str, JsonValue],
        *,
        duration_ms: int | None = None,
        commit: bool = True,
    ) -> None:
        await self._traces.append_event(
            tenant_id,
            trace_id,
            TraceEventCreate(
                event_id=_event_id(),
                event_type=event_type,
                status=status,
                payload=payload,
                duration_ms=duration_ms,
            ),
            commit=commit,
        )

    async def _finish_failure(
        self,
        payload: ChatRequest,
        *,
        identity: AuthContext,
        trace_id: str,
        status: TraceStatus,
        code: str,
        request_fingerprint: str,
        fencing_token: int | None,
        lease_guard: SessionLeaseGuard | None,
        active_skill_calls: dict[str, ActiveSkillCall],
        skill_audit_events: list[TraceEventCreate],
    ) -> bool:
        try:
            # A memory tool may have staged encrypted facts before the agent
            # fails. Clear the shared unit of work before recording the durable
            # failure Trace, otherwise a failure transition could commit it.
            await self._conversation.rollback()
            if fencing_token is not None:
                allowed = await self._conversation.lock_trace_failure_fence(
                    payload.session_id,
                    tenant_id=identity.tenant_id,
                    actor_id=identity.actor_id,
                    fencing_token=fencing_token,
                    trace_id=trace_id,
                )
                if not allowed:
                    return False
            if lease_guard is not None:
                await lease_guard.assert_owned()
            for event in skill_audit_events:
                await self._traces.append_event(
                    identity.tenant_id,
                    trace_id,
                    event,
                    commit=False,
                )
            skill_terminal_status = (
                TraceEventStatus.CANCELLED
                if status is TraceStatus.CANCELLED
                else TraceEventStatus.FAILED
            )
            skill_outcome = "cancelled" if status is TraceStatus.CANCELLED else "failed"
            for started_at, skill_id, version in active_skill_calls.values():
                duration_ms = bounded_trace_duration_ms(time.monotonic() - started_at)
                await self._traces.append_event(
                    identity.tenant_id,
                    trace_id,
                    TraceEventCreate(
                        event_id=_event_id(),
                        event_type=TraceEventType.SKILL_EXECUTE,
                        status=skill_terminal_status,
                        payload={
                            "duration_ms": duration_ms,
                            "error_code": code.casefold(),
                            "operation": "viewer",
                            "outcome": skill_outcome,
                            "skill": skill_id,
                            "success": False,
                            **({"version": version} if version else {}),
                        },
                        duration_ms=duration_ms,
                    ),
                    commit=False,
                )
            await self._traces.append_event(
                identity.tenant_id,
                trace_id,
                TraceEventCreate(
                    event_id=_event_id(),
                    event_type=TraceEventType.SYSTEM_ERROR,
                    status=(
                        TraceEventStatus.CANCELLED
                        if status is TraceStatus.CANCELLED
                        else TraceEventStatus.FAILED
                    ),
                    payload={
                        "error_code": code,
                        "module": "agent_harness",
                        "operation": "process_message",
                        "result_code": code,
                    },
                ),
                commit=False,
            )
            await self._traces.finish_trace(
                identity.tenant_id,
                trace_id,
                TraceFinishRequest(
                    idempotency_key=_finish_id(),
                    status=status,
                    error_code=code.casefold(),
                    error_summary="chat execution did not complete",
                    attributes={
                        "outcome": status.value,
                        "request_fingerprint": request_fingerprint,
                        "success": False,
                    },
                ),
            )
            return True
        except Exception:
            await self._conversation.rollback()
            # Callers must never publish a terminal cancellation unless this
            # transaction actually committed the corresponding Trace state.
            return False

    async def _emit_replay(
        self,
        response: AgentResponse,
        *,
        trace_id: str,
        session_id: uuid.UUID,
        callback: StreamCallback,
    ) -> None:
        await callback(
            StreamEvent(
                event_type="agent_start",
                data={"agent": "gerclaw_geriatric_specialist", "status": "replay"},
                timestamp=datetime.now(UTC),
            )
        )
        for start in range(0, len(response.text), 80):
            await callback(
                StreamEvent(
                    event_type="text_delta",
                    data={"content": response.text[start : start + 80]},
                    timestamp=datetime.now(UTC),
                )
            )
        rendered = await self._input_output.render(response, "web")
        done = ChatDoneData(
            full_text=rendered["text"],
            references=rendered["citations"],
            safety=rendered["safety"],
            trace_id=trace_id,
            session_id=session_id,
            replayed=True,
        )
        await callback(
            StreamEvent(
                event_type="done",
                data=done.model_dump(mode="json"),
                timestamp=datetime.now(UTC),
            )
        )

    @staticmethod
    def error_code(error: Exception) -> str:
        """Map internal exceptions to stable, non-provider public codes."""

        name = type(error).__name__
        mapping = {
            "SessionBusyError": "CHAT_SESSION_BUSY",
            "SessionLeaseUnavailableError": "CHAT_COORDINATION_UNAVAILABLE",
            "SessionLeaseLostError": "CHAT_COORDINATION_UNAVAILABLE",
            "ConversationConflictError": "CHAT_CONFLICT",
            "ConversationNotFoundError": "CHAT_SESSION_NOT_FOUND",
            "EvidenceUnavailableError": "CHAT_EVIDENCE_UNAVAILABLE",
            "RAGUnavailableError": "CHAT_EVIDENCE_UNAVAILABLE",
            "ModelChainExhaustedError": "CHAT_MODEL_UNAVAILABLE",
            "PartialModelStreamError": "CHAT_MODEL_STREAM_INTERRUPTED",
            "AgentIterationLimitError": "CHAT_ITERATION_LIMIT",
            "RuntimeBudgetExceededError": "CHAT_RUNTIME_BUDGET_EXCEEDED",
            "AgentApprovalRequiredError": "CHAT_APPROVAL_REQUIRED",
            "UnsupportedAgentContextError": "CHAT_CONTEXT_UNSUPPORTED",
            "WorkflowContextError": "CHAT_CONTEXT_UNSUPPORTED",
            "DocumentContextError": "CHAT_DOCUMENT_UNAVAILABLE",
            "EmptyAgentResponseError": "CHAT_EMPTY_RESPONSE",
            "AgentScopeMemoryAdapterError": "CHAT_MEMORY_UNAVAILABLE",
            "MemoryDataError": "CHAT_MEMORY_UNAVAILABLE",
            "MemoryExtractionError": "CHAT_MEMORY_UNAVAILABLE",
            "MemoryRepositoryError": "CHAT_MEMORY_UNAVAILABLE",
            "MemoryStoreError": "CHAT_MEMORY_UNAVAILABLE",
            "SkillNotFoundError": "CHAT_SKILL_UNAVAILABLE",
            "SkillDisabledError": "CHAT_SKILL_UNAVAILABLE",
            "CorruptSkillError": "CHAT_SKILL_UNAVAILABLE",
            "ChatCancellationFinalizationError": "CHAT_CANCELLATION_FINALIZATION_FAILED",
        }
        return mapping.get(name, "CHAT_EXECUTION_FAILED")

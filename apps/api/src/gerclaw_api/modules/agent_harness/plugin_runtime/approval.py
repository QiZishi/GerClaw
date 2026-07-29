"""Durable human-approval parking for governed AgentScope tools."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import cast

from agentscope.message import ToolCallBlock
from pydantic import BaseModel, ValidationError

from gerclaw_api.modules.agent_harness.run_lifecycle import AgentApprovalRequiredError
from gerclaw_api.modules.contracts import ExecutionContext
from gerclaw_api.modules.runtime.models import (
    ApprovalCreate,
    ApprovalRead,
    RuntimePrincipal,
    ToolCapability,
    ToolInvocationRequest,
)
from gerclaw_api.modules.runtime.permission import POLICY_VERSION
from gerclaw_api.security import JsonValue

ApprovalCallback = Callable[[ApprovalCreate], Awaitable[ApprovalRead]]
ApprovalEventEmitter = Callable[[str, dict[str, JsonValue]], Awaitable[None]]


class ApprovalCoordinator:
    """Validate and persist all pending side-effect requests before returning."""

    def __init__(
        self,
        *,
        callback: ApprovalCallback | None,
        principal: RuntimePrincipal,
        execution: ExecutionContext,
        ttl_seconds: int,
    ) -> None:
        self._callback = callback
        self._principal = principal
        self._execution = execution
        self._ttl_seconds = ttl_seconds

    async def persist(
        self,
        tool_calls: list[ToolCallBlock],
        *,
        capabilities: dict[str, ToolCapability],
        input_models: dict[str, type[BaseModel]],
        emit: ApprovalEventEmitter,
    ) -> tuple[str, ...]:
        """Park every AgentScope ASK in durable HITL before ending this turn."""

        if self._callback is None:
            raise AgentApprovalRequiredError(
                "approval persistence is unavailable; action was not executed"
            )
        if self._principal.user_id is None:
            raise AgentApprovalRequiredError("approval requires a verified user identity")
        approval_ids: list[str] = []
        for tool_call in tool_calls:
            capability = capabilities.get(tool_call.name)
            input_model = input_models.get(tool_call.name)
            if capability is None or input_model is None or not capability.approval_roles:
                raise AgentApprovalRequiredError(
                    "requested tool has no approved human-review capability"
                )
            try:
                raw_arguments = json.loads(tool_call.input)
            except json.JSONDecodeError as error:
                raise AgentApprovalRequiredError(
                    "requested tool arguments are not valid JSON"
                ) from error
            if not isinstance(raw_arguments, dict):
                raise AgentApprovalRequiredError("requested tool arguments must be an object")
            try:
                validated_arguments = input_model.model_validate(raw_arguments).model_dump(
                    mode="json"
                )
            except ValidationError as error:
                raise AgentApprovalRequiredError(
                    "requested tool arguments failed the registered schema"
                ) from error
            digest = hashlib.sha256(
                f"{self._execution.trace_id}:{tool_call.id}:{tool_call.input}".encode()
            ).hexdigest()
            command = ApprovalCreate(
                user_id=self._principal.user_id,
                patient_id=self._principal.patient_id,
                session_id=self._execution.session_id,
                trace_id=self._execution.trace_id,
                invocation=ToolInvocationRequest(
                    invocation_id=f"invoke_{digest[:32]}",
                    tool_name=capability.name,
                    tool_version=capability.version,
                    arguments=cast(dict[str, JsonValue], validated_arguments),
                    idempotency_key=f"idem_{digest}",
                    outbound_data_redacted=False,
                ),
                required_roles=tuple(
                    sorted(capability.approval_roles, key=lambda role: role.value)
                ),
                policy_version=POLICY_VERSION,
                expires_at=datetime.now(UTC) + timedelta(seconds=self._ttl_seconds),
            )
            approval = await self._callback(command)
            approval_id = str(approval.id)
            approval_ids.append(approval_id)
            await emit(
                "approval_required",
                {
                    "approval_id": approval_id,
                    "tool_name": approval.tool_name,
                    "status": approval.status.value,
                    "expires_at": approval.expires_at.isoformat(),
                    "policy_version": approval.policy_version,
                    "tool_version": approval.tool_version,
                },
            )
        return tuple(approval_ids)

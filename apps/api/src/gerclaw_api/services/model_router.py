"""AgentScope-compatible ordered model failover with concurrency-safe audit capture."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from agentscope.message import Msg, ThinkingBlock
from agentscope.model import ChatModelBase, ChatResponse
from agentscope.tool import ToolChoice
from pydantic import BaseModel

from gerclaw_api.config import AgentModelConfig
from gerclaw_api.metrics import AGENT_MODEL_ATTEMPTS
from gerclaw_api.modules.privacy_redaction.models import (
    RedactionCategory,
    RedactionFinding,
    RedactionResult,
)
from gerclaw_api.modules.privacy_redaction.policy import (
    MODEL_PROMPT_REDACTION_POLICY_VERSION,
    PrivacyRedactionError,
    redact_external_model_prompt,
)
from gerclaw_api.services.model_factory import build_agentscope_model, close_agentscope_model


class ModelChainExhaustedError(RuntimeError):
    """Raised after every configured real model failed before visible output."""


class PartialModelStreamError(RuntimeError):
    """Raised when failover would duplicate already-visible model output."""


class ModelPromptPrivacyError(RuntimeError):
    """Raised when model-bound prompt data cannot pass the privacy boundary."""


class ModelPromptEgressAuditError(RuntimeError):
    """Raised when the required model-provider audit boundary is unavailable."""


@dataclass(frozen=True, slots=True)
class ModelAttempt:
    """Safe audit record containing slots and reason codes, never provider text."""

    preference: Literal["primary", "backup1", "backup2"]
    outcome: Literal["started", "succeeded", "failed", "failed_partial"]
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class _Candidate:
    preference: Literal["primary", "backup1", "backup2"]
    model: ChatModelBase
    timeout_seconds: float


class ModelPromptEgressAudit(Protocol):
    """Persist a PHI-free outcome around one provider attempt."""

    async def prepare(
        self,
        *,
        preference: Literal["primary", "backup1", "backup2"],
        decision: RedactionResult,
    ) -> object: ...

    async def finish(self, handle: object, *, outcome: Literal["succeeded", "failed"]) -> None: ...


_ATTEMPT_CAPTURE: ContextVar[list[ModelAttempt] | None] = ContextVar(
    "gerclaw_model_attempt_capture", default=None
)
_EGRESS_AUDIT: ContextVar[ModelPromptEgressAudit | None] = ContextVar(
    "gerclaw_model_prompt_egress_audit", default=None
)


@contextmanager
def capture_model_attempts() -> Iterator[list[ModelAttempt]]:
    """Capture attempts in the current async context without shared mutable state."""

    attempts: list[ModelAttempt] = []
    token = _ATTEMPT_CAPTURE.set(attempts)
    try:
        yield attempts
    finally:
        _ATTEMPT_CAPTURE.reset(token)


@contextmanager
def bind_model_prompt_egress_audit(audit: ModelPromptEgressAudit) -> Iterator[None]:
    """Bind one request-owned audit sink without sharing caller identity globally."""

    token = _EGRESS_AUDIT.set(audit)
    try:
        yield
    finally:
        _EGRESS_AUDIT.reset(token)


def _record(attempt: ModelAttempt) -> None:
    AGENT_MODEL_ATTEMPTS.labels(preference=attempt.preference, outcome=attempt.outcome).inc()
    capture = _ATTEMPT_CAPTURE.get()
    if capture is not None:
        capture.append(attempt)


def _safe_error_code(error: Exception) -> str:
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return "MODEL_TIMEOUT"
    status = getattr(error, "status_code", None)
    if status == 429:
        return "MODEL_RATE_LIMITED"
    if isinstance(status, int) and 500 <= status <= 599:
        return "MODEL_SERVER_ERROR"
    return "MODEL_UNAVAILABLE"


def _commits_stream(chunk: ChatResponse) -> bool:
    """Return true once retrying could duplicate visible/tool-call output."""

    for block in chunk.content:
        if isinstance(block, ThinkingBlock):
            continue
        text = getattr(block, "text", None)
        if isinstance(text, str) and not text.strip():
            continue
        return True
    return False


def _redact_model_value(value: Any, decisions: list[RedactionResult]) -> Any:
    """Redact only provider-bound string values while preserving AgentScope blocks."""

    if isinstance(value, str):
        if not value.strip():
            return value
        try:
            decision = redact_external_model_prompt(value)
            decisions.append(decision)
            return decision.text
        except PrivacyRedactionError as error:
            raise ModelPromptPrivacyError("model prompt cannot pass privacy policy") from error
    if isinstance(value, list):
        return [_redact_model_value(item, decisions) for item in value]
    if isinstance(value, dict):
        return {key: _redact_model_value(item, decisions) for key, item in value.items()}
    return value


def redact_model_messages(messages: list[Msg]) -> list[Msg]:
    """Return provider-safe message copies without mutating local Agent state."""

    safe_messages, _ = redact_model_messages_with_decision(messages)
    return safe_messages


def redact_model_messages_with_decision(messages: list[Msg]) -> tuple[list[Msg], RedactionResult]:
    """Return provider copies plus one bounded, PHI-free egress summary."""

    decisions: list[RedactionResult] = []
    safe_messages = [
        Msg.model_validate(_redact_model_value(message.model_dump(), decisions))
        for message in messages
    ]
    if not decisions:
        raise ModelPromptPrivacyError("model prompt cannot be empty")
    counts: dict[RedactionCategory, int] = {}
    for decision in decisions:
        for finding in decision.findings:
            counts[finding.category] = counts.get(finding.category, 0) + finding.count
    try:
        findings = tuple(
            RedactionFinding(category=category, count=count)
            for category, count in sorted(counts.items(), key=lambda item: item[0].value)
        )
        return safe_messages, RedactionResult(
            text="[MODEL_PROMPT_REDACTED]",
            purpose=decisions[0].purpose,
            policy_version=MODEL_PROMPT_REDACTION_POLICY_VERSION,
            findings=findings,
        )
    except ValueError as error:
        raise ModelPromptPrivacyError("model prompt cannot pass privacy policy") from error


async def _prepare_egress(
    preference: Literal["primary", "backup1", "backup2"], decision: RedactionResult
) -> object | None:
    audit = _EGRESS_AUDIT.get()
    if audit is None:
        return None
    try:
        return await audit.prepare(preference=preference, decision=decision)
    except Exception as error:
        raise ModelPromptEgressAuditError("model prompt egress audit is unavailable") from error


async def _finish_egress(handle: object | None, *, outcome: Literal["succeeded", "failed"]) -> None:
    if handle is None:
        return
    audit = _EGRESS_AUDIT.get()
    if audit is None:
        raise ModelPromptEgressAuditError("model prompt egress audit context was lost")
    try:
        await audit.finish(handle, outcome=outcome)
    except Exception as error:
        raise ModelPromptEgressAuditError("model prompt egress audit is unavailable") from error


class FailoverChatModel(ChatModelBase):
    """Route one AgentScope model call through primary and two backups."""

    class Parameters(BaseModel):
        """The router has no provider-specific generation parameters."""

    def __init__(self, configs: tuple[AgentModelConfig, ...]) -> None:
        if len(configs) != 3:
            raise ValueError("GerClaw failover requires exactly three configured models")
        candidates = tuple(
            _Candidate(
                config.preference,
                build_agentscope_model(config),
                config.timeout_seconds,
            )
            for config in configs
        )
        self._candidates = candidates
        super().__init__(
            credential=candidates[0].model.credential,
            model="gerclaw-failover-chain",
            parameters=self.Parameters(),
            stream=True,
            max_retries=0,
            context_size=min(candidate.model.context_size for candidate in candidates),
        )

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        del model_name
        safe_messages, decision = redact_model_messages_with_decision(messages)
        for index, candidate in enumerate(self._candidates):
            _record(ModelAttempt(candidate.preference, "started"))
            egress_handle = await _prepare_egress(candidate.preference, decision)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + candidate.timeout_seconds
            try:
                async with asyncio.timeout_at(deadline):
                    response = await candidate.model(
                        messages=safe_messages,
                        tools=tools,
                        tool_choice=tool_choice,
                        **kwargs,
                    )
                if loop.time() >= deadline:
                    raise TimeoutError("model call exceeded its total deadline")
            except asyncio.CancelledError:
                await _finish_egress(egress_handle, outcome="failed")
                raise
            except ModelPromptEgressAuditError:
                raise
            except Exception as error:
                await _finish_egress(egress_handle, outcome="failed")
                _record(ModelAttempt(candidate.preference, "failed", _safe_error_code(error)))
                continue

            if isinstance(response, ChatResponse):
                if _commits_stream(response):
                    await _finish_egress(egress_handle, outcome="succeeded")
                    _record(ModelAttempt(candidate.preference, "succeeded"))
                    return response
                await _finish_egress(egress_handle, outcome="failed")
                _record(ModelAttempt(candidate.preference, "failed", "MODEL_EMPTY_RESPONSE"))
                continue
            return self._stream_with_failover(
                index,
                response,
                safe_messages,
                tools,
                tool_choice,
                kwargs,
                deadline,
                egress_handle,
                decision,
            )
        raise ModelChainExhaustedError("all configured model services are unavailable")

    async def _stream_with_failover(
        self,
        start_index: int,
        initial: AsyncGenerator[ChatResponse, None],
        messages: list[Msg],
        tools: list[dict[str, Any]] | None,
        tool_choice: ToolChoice | None,
        kwargs: dict[str, Any],
        deadline: float,
        egress_handle: object | None,
        decision: RedactionResult,
    ) -> AsyncGenerator[ChatResponse, None]:
        current_index = start_index
        stream = initial
        while current_index < len(self._candidates):
            candidate = self._candidates[current_index]
            committed = False
            try:
                async with asyncio.timeout_at(deadline):
                    async for chunk in stream:
                        chunk_committed = _commits_stream(chunk)
                        committed = committed or chunk_committed
                        if chunk_committed or (
                            not chunk.is_last
                            and chunk.content
                            and all(isinstance(block, ThinkingBlock) for block in chunk.content)
                        ):
                            yield chunk
                # Some provider/AgentScope stream wrappers turn task
                # cancellation into a clean iterator end. Deadline expiry is
                # still authoritative even when no TimeoutError propagates.
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError("model stream exceeded its total deadline")
                if committed:
                    await _finish_egress(egress_handle, outcome="succeeded")
                    _record(ModelAttempt(candidate.preference, "succeeded"))
                    return
                await _finish_egress(egress_handle, outcome="failed")
                _record(ModelAttempt(candidate.preference, "failed", "MODEL_EMPTY_RESPONSE"))
            except asyncio.CancelledError:
                await _finish_egress(egress_handle, outcome="failed")
                raise
            except ModelPromptEgressAuditError:
                raise
            except Exception as error:
                code = _safe_error_code(error)
                if committed:
                    await _finish_egress(egress_handle, outcome="failed")
                    _record(ModelAttempt(candidate.preference, "failed_partial", code))
                    raise PartialModelStreamError(
                        "model stream failed after visible output; automatic replay is unsafe"
                    ) from error
                _record(ModelAttempt(candidate.preference, "failed", code))
                await _finish_egress(egress_handle, outcome="failed")

            while True:
                current_index += 1
                if current_index >= len(self._candidates):
                    raise ModelChainExhaustedError("all configured model services are unavailable")
                next_candidate = self._candidates[current_index]
                _record(ModelAttempt(next_candidate.preference, "started"))
                egress_handle = await _prepare_egress(next_candidate.preference, decision)
                loop = asyncio.get_running_loop()
                deadline = loop.time() + next_candidate.timeout_seconds
                try:
                    async with asyncio.timeout_at(deadline):
                        next_response = await next_candidate.model(
                            messages=messages,
                            tools=tools,
                            tool_choice=tool_choice,
                            **kwargs,
                        )
                    if loop.time() >= deadline:
                        raise TimeoutError("model call exceeded its total deadline")
                except asyncio.CancelledError:
                    await _finish_egress(egress_handle, outcome="failed")
                    raise
                except ModelPromptEgressAuditError:
                    raise
                except Exception as error:
                    await _finish_egress(egress_handle, outcome="failed")
                    _record(
                        ModelAttempt(
                            next_candidate.preference,
                            "failed",
                            _safe_error_code(error),
                        )
                    )
                    continue
                if isinstance(next_response, ChatResponse):
                    if _commits_stream(next_response):
                        await _finish_egress(egress_handle, outcome="succeeded")
                        _record(ModelAttempt(next_candidate.preference, "succeeded"))
                        yield next_response
                        return
                    _record(
                        ModelAttempt(
                            next_candidate.preference,
                            "failed",
                            "MODEL_EMPTY_RESPONSE",
                        )
                    )
                    await _finish_egress(egress_handle, outcome="failed")
                    continue
                stream = next_response
                break
        raise ModelChainExhaustedError("all configured model services are unavailable")

    @property
    def candidate_models(self) -> tuple[ChatModelBase, ...]:
        """Expose owned clients for lifecycle cleanup without provider branching."""

        return tuple(candidate.model for candidate in self._candidates)

    async def aclose(self) -> None:
        """Close all provider HTTP clients owned by this router."""

        for candidate in self._candidates:
            await close_agentscope_model(candidate.model)

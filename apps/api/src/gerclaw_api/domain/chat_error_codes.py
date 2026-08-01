"""Server-owned stable Chat error-code allowlist shared by API and telemetry."""
# ruff: noqa: RUF001 -- Reader-facing Chinese copy intentionally uses CJK punctuation.

from __future__ import annotations

CHAT_ERROR_CODE_BY_EXCEPTION: dict[str, str] = {
    "SessionBusyError": "CHAT_SESSION_BUSY",
    "SessionLeaseUnavailableError": "CHAT_COORDINATION_UNAVAILABLE",
    "SessionLeaseLostError": "CHAT_COORDINATION_UNAVAILABLE",
    "ConversationConflictError": "CHAT_CONFLICT",
    "ConversationNotFoundError": "CHAT_SESSION_NOT_FOUND",
    "RunRegenerationNotFoundError": "CHAT_REGENERATION_NOT_FOUND",
    "RunRegenerationConflictError": "CHAT_REGENERATION_CONFLICT",
    "AnswerVersionConflictError": "CHAT_REGENERATION_CONFLICT",
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
    "AgentOutputProtocolError": "CHAT_OUTPUT_CONTRACT_INVALID",
    "AgentScopeMemoryAdapterError": "CHAT_MEMORY_UNAVAILABLE",
    "MemoryDataError": "CHAT_MEMORY_UNAVAILABLE",
    "MemoryExtractionError": "CHAT_MEMORY_UNAVAILABLE",
    "MemoryRepositoryError": "CHAT_MEMORY_UNAVAILABLE",
    "MemoryStoreError": "CHAT_MEMORY_UNAVAILABLE",
    "SkillNotFoundError": "CHAT_SKILL_UNAVAILABLE",
    "SkillDisabledError": "CHAT_SKILL_UNAVAILABLE",
    "CorruptSkillError": "CHAT_SKILL_UNAVAILABLE",
    "ChatCancellationFinalizationError": ("CHAT_CANCELLATION_FINALIZATION_FAILED"),
}
CHAT_FALLBACK_ERROR_CODE = "CHAT_EXECUTION_FAILED"
CHAT_CANCELLATION_ERROR_CODE = "CHAT_CANCELLED"
CHAT_ERROR_CODES = frozenset(
    {
        *CHAT_ERROR_CODE_BY_EXCEPTION.values(),
        CHAT_FALLBACK_ERROR_CODE,
        CHAT_CANCELLATION_ERROR_CODE,
    }
)

_PUBLIC_CHAT_ERRORS: dict[str, tuple[str, bool]] = {
    "CHAT_SESSION_BUSY": ("该会话正在生成，请等待当前回复完成后再试。", True),
    "CHAT_COORDINATION_UNAVAILABLE": ("服务暂时不稳定，请稍后重试。", True),
    "CHAT_SESSION_NOT_FOUND": ("会话不存在或无权访问。", False),
    "CHAT_CONFLICT": ("当前会话内容已经变化，请刷新后重试。", False),
    "CHAT_REGENERATION_NOT_FOUND": ("原回答不存在或无权重新生成。", False),
    "CHAT_REGENERATION_CONFLICT": ("原回答或上下文已变化，请刷新后重新生成。", False),
    "CHAT_EVIDENCE_UNAVAILABLE": ("这次回答没有完整生成，请稍后重试。", True),
    "CHAT_MODEL_UNAVAILABLE": ("服务暂时不稳定，这次回答没有完整生成。请稍后重试。", True),
    "CHAT_MODEL_STREAM_INTERRUPTED": (
        "服务暂时不稳定，这次回答没有完整生成。请稍后重试。",
        True,
    ),
    "CHAT_ITERATION_LIMIT": ("这次回答没有完整生成，请重试。", True),
    "CHAT_RUNTIME_BUDGET_EXCEEDED": ("这次回答没有完整生成，请重试。", True),
    "CHAT_APPROVAL_REQUIRED": ("这项操作需要医生确认，当前尚未执行。", False),
    "CHAT_CONTEXT_UNSUPPORTED": ("当前内容暂时无法处理，请调整后重试。", False),
    "CHAT_DOCUMENT_UNAVAILABLE": ("所选文件不可用，请重新上传后重试。", False),
    "CHAT_EMPTY_RESPONSE": ("这次回答没有完整生成，请重试。", True),
    "CHAT_OUTPUT_CONTRACT_INVALID": ("这次回答没有完整生成，请重试。", True),
    "CHAT_MEMORY_UNAVAILABLE": ("服务暂时不稳定，这次回答没有完整生成。请稍后重试。", True),
    "CHAT_SKILL_UNAVAILABLE": ("所选技能暂时不可用，请刷新后重试。", False),
    "CHAT_CANCELLATION_FINALIZATION_FAILED": ("暂时无法停止，请稍后重试。", True),
}
_DEFAULT_PUBLIC_CHAT_ERROR = ("这次回答没有完整生成，请重试。", True)


def public_chat_error_code(error: Exception) -> str:
    """Map an internal exception type to an allowlisted non-provider code."""

    return CHAT_ERROR_CODE_BY_EXCEPTION.get(
        type(error).__name__,
        CHAT_FALLBACK_ERROR_CODE,
    )


def public_chat_error(code: str) -> tuple[str, bool]:
    """Return concise reader-facing copy without leaking operational details."""

    normalized = code.upper()
    if any(marker in normalized for marker in ("CONTENT_POLICY", "MODERATION", "SENSITIVE")):
        return ("你的需求中有目前无法处理的敏感内容，请调整后再试。", False)
    return _PUBLIC_CHAT_ERRORS.get(normalized, _DEFAULT_PUBLIC_CHAT_ERROR)

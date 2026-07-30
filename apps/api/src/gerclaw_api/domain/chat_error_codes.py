"""Server-owned stable Chat error-code allowlist shared by API and telemetry."""

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


def public_chat_error_code(error: Exception) -> str:
    """Map an internal exception type to an allowlisted non-provider code."""

    return CHAT_ERROR_CODE_BY_EXCEPTION.get(
        type(error).__name__,
        CHAT_FALLBACK_ERROR_CODE,
    )

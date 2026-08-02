"""Server-owned chat error codes and the reader-facing delivery fallback."""
# ruff: noqa: RUF001 -- Reader-facing Chinese copy intentionally uses CJK punctuation.

from __future__ import annotations

import re

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
_PUBLIC_MEDICAL_DISCLAIMER = "内容由 AI 生成，仅供参考。身体不适请及时就医。"
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]+")
_MAX_ECHOED_QUESTION_CHARACTERS = 240


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


def _reader_question(user_message: str) -> str:
    """Keep the original intent visible without echoing control characters."""

    compact = _CONTROL_CHARACTERS.sub(" ", user_message)
    compact = " ".join(compact.split())
    if not compact:
        return "你刚才的问题"
    return compact[:_MAX_ECHOED_QUESTION_CHARACTERS]


def public_chat_fallback(
    _code: str,
    user_message: str = "",
    *,
    medical_content: bool = False,
) -> tuple[str, bool]:
    """Return a useful terminal answer for any failed execution path.

    The model/provider failure remains private telemetry.  The public channel
    receives a natural-language result tied to the user's request, so a
    runtime failure cannot turn into an internal prompt or an empty message.
    This is deliberately topic-agnostic: the medical branch changes only the
    safe next-step content and disclaimer, never the failure classification.
    """

    question = _reader_question(user_message)
    if medical_content:
        return (
            f"我理解你想解决的是：“{question}”。\n\n"
            "这次暂时没有完成完整的个性化分析，我先把安全的下一步说清楚：\n\n"
            "1. 如果症状突然出现、明显加重，或伴有胸痛、呼吸困难、意识或言语异常，"
            "请立即就医，不要等待在线回复。\n"
            "2. 记下症状开始时间、变化情况、测量值或检查结果，以及正在使用的药物；"
            "不要自行停药、加量、换药。\n"
            "3. 把年龄、主要症状、持续时间和相关记录补充给我，我会继续围绕原问题回答。\n\n"
            f"{_PUBLIC_MEDICAL_DISCLAIMER}",
            True,
        )
    return (
        f"我理解你想问的是：“{question}”。\n\n"
        "这次暂时没有完成完整回答。请再发一次，或补充你希望得到的结果（例如解释、步骤、比较或方案），我会继续围绕这个问题回答。",
        True,
    )

"""Real-model, evidence-bound extraction of user-authored health memories."""

# ruff: noqa: RUF001 -- Chinese medical prompts intentionally use CJK punctuation.

from __future__ import annotations

import unicodedata
from typing import Any, Protocol

from agentscope.message import Msg, SystemMsg, UserMsg
from agentscope.model import StructuredResponse
from pydantic import BaseModel, ValidationError

from gerclaw_api.modules.memory.models import ExtractedMemoryFact, MemoryExtraction
from gerclaw_api.security import redact_text

_SYSTEM_PROMPT = """你是 GerClaw 的医疗记忆抽取器。只抽取用户在本条消息中明确自述的事实。

安全规则：
1. 禁止从症状推断诊断，禁止补全用户没有说出的药名、剂量、疾病或时间。
2. evidence_span 必须逐字复制自用户消息，且能独立证明该事实。
3. 否认、停药、已解决或更正使用 action=deactivate，不得写成仍然有效。
4. 过敏、慢病、用药、生命体征等只记录用户明确陈述；不确定内容降低 confidence。
5. 身份证、手机号、邮箱、地址、姓名等身份信息不得抽取。
6. 没有值得长期记忆的事实时返回空 facts。

category 使用固定枚举；memory_type 中长期稳定事实用 stable，持续变化状态用 evolving，
有明确时间的跌倒/急诊/手术等事件用 event。statement 使用“用户自述……”表述，不得升级为医生确诊。
"""

_NEGATION_MARKERS = (
    "没有",
    "并无",
    "无过敏",
    "不过敏",
    "未患",
    "没患",
    "不再",
    "停药",
    "停用",
    "停止服用",
    "已经好了",
    "已恢复",
    "不是",
)


class StructuredMemoryModel(Protocol):
    """Narrow AgentScope structured-output surface used by the extractor."""

    async def generate_structured_output(
        self,
        messages: list[Msg],
        structured_model: type[BaseModel] | dict[Any, Any],
        **kwargs: Any,
    ) -> StructuredResponse: ...


class MemoryExtractionError(RuntimeError):
    """Safe failure that never includes model output or user text."""


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


class RealMemoryExtractor:
    """Use configured AgentScope failover while enforcing source evidence in code."""

    def __init__(
        self,
        model: StructuredMemoryModel,
        *,
        min_confidence: float,
        max_facts: int,
    ) -> None:
        self._model = model
        self._min_confidence = min_confidence
        self._max_facts = max_facts

    async def extract(self, user_text: str) -> list[tuple[ExtractedMemoryFact, str]]:
        """Return candidates paired with deterministic confirmed/pending/inactive status."""

        safe_text = _normalized(redact_text(user_text))
        if not safe_text or len(safe_text) > 4_000:
            raise ValueError("memory extraction input must contain 1 to 4,000 characters")
        try:
            response = await self._model.generate_structured_output(
                [
                    SystemMsg(name="memory_policy", content=_SYSTEM_PROMPT),
                    UserMsg(
                        name="user",
                        content=(
                            f"<untrusted-user-statement>\n{safe_text}\n</untrusted-user-statement>"
                        ),
                    ),
                ],
                MemoryExtraction,
            )
            extraction = MemoryExtraction.model_validate(response.content)
        except ValidationError as error:
            raise MemoryExtractionError("memory model returned an invalid schema") from error
        except Exception as error:
            raise MemoryExtractionError("memory model extraction failed") from error

        validated: list[tuple[ExtractedMemoryFact, str]] = []
        seen: set[tuple[str, str]] = set()
        for fact in extraction.facts[: self._max_facts]:
            evidence = _normalized(fact.evidence_span)
            if not evidence or evidence not in safe_text:
                continue
            key = (fact.category, _normalized(fact.entity).casefold())
            if key in seen:
                continue
            seen.add(key)
            has_negation = any(marker in evidence for marker in _NEGATION_MARKERS)
            if fact.action == "deactivate":
                status = "inactive"
            elif has_negation:
                status = "pending"
            elif fact.confidence >= self._min_confidence:
                status = "confirmed"
            else:
                status = "pending"
            validated.append((fact, status))
        return validated

"""AgentScope ContextConfig compression with medical-critical preservation."""

# ruff: noqa: RUF001 -- Chinese medical prompts intentionally use CJK punctuation.

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from agentscope.agent import Agent, ContextConfig
from agentscope.message import AssistantMsg, HintBlock, Msg, UserMsg
from agentscope.model import ChatModelBase
from agentscope.state import AgentState
from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.modules.memory.protocols import MemoryMessage
from gerclaw_api.token_estimation import estimate_text_tokens

_COMPRESSION_INSTRUCTIONS = HintBlock(
    hint=(
        "压缩时必须保留：用户明确自述的全部过敏史、当前和已停用药物及剂量、"
        "慢病来源状态、生命体征数值与时间、跌倒/急诊/自伤等红旗事件、"
        "仍待确认的问题。禁止把症状升级成诊断，禁止编造未出现的事实。"
    ),
    source="system",
)
_FALLBACK_SEGMENT = re.compile(r"[^。！？!?\n]+(?:[。！？!?]+|\n+|$)")
_FALLBACK_CRITICAL = re.compile(
    r"过敏|药|剂量|停用|血压|血糖|心率|胸痛|呼吸困难|意识|偏瘫|"
    r"出血|自伤|跌倒|检查|化验|手术|住院|急诊|否认|没有|不"
)


class MedicalContextSummary(BaseModel):
    """Schema required from AgentScope's structured compression call."""

    model_config = ConfigDict(extra="forbid")

    task_overview: str = Field(max_length=4_000)
    current_state: str = Field(max_length=4_000)
    important_discoveries: str = Field(max_length=4_000)
    next_steps: str = Field(max_length=4_000)
    context_to_preserve: str = Field(max_length=6_000)
    allergies: str = Field(max_length=2_000)
    current_medications: str = Field(max_length=3_000)
    red_flags: str = Field(max_length=2_000)
    pending_confirmations: str = Field(max_length=2_000)


_SUMMARY_TEMPLATE = """<system-info source="encrypted-session-summary">
# 对话任务概述
{task_overview}
# 当前状态
{current_state}
# 重要医疗发现
{important_discoveries}
# 过敏史（必须优先核验）
{allergies}
# 当前及近期用药
{current_medications}
# 红旗风险事件
{red_flags}
# 待确认信息
{pending_confirmations}
# 后续步骤
{next_steps}
# 必须继续保留的上下文
{context_to_preserve}
</system-info>"""


@dataclass(frozen=True, slots=True)
class CompressionResult:
    """Projected messages plus the encrypted-summary value to persist."""

    messages: list[MemoryMessage]
    summary: str
    compressed: bool


def compression_source_hash(
    messages: list[MemoryMessage],
    *,
    max_tokens: int,
) -> str:
    """Hash exact source messages and budget for encrypted projection reuse."""

    payload = {
        "schema_version": "medical-context-compression-v1",
        "max_tokens": max_tokens,
        "messages": [item.model_dump(mode="json") for item in messages],
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _to_agent_message(message: MemoryMessage) -> Msg | None:
    text = message.text()
    if not text:
        return None
    if message.role == "user":
        return UserMsg(name="user", content=text)
    if message.role == "assistant":
        return AssistantMsg(name="GerClaw", content=text)
    return None


def _from_agent_message(message: Msg) -> MemoryMessage | None:
    if message.role not in {"user", "assistant"}:
        return None
    raw_text = message.get_text_content()
    text = raw_text.strip() if raw_text else ""
    if not text:
        return None
    return MemoryMessage(role=message.role, content=[{"type": "text", "text": text}])


class AgentScopeContextCompressor:
    """Run AgentScope's native compression over PostgreSQL-backed history."""

    def __init__(self, model: ChatModelBase) -> None:
        self._model = model

    async def compress(
        self,
        messages: list[MemoryMessage],
        *,
        session_id: str,
        max_tokens: int,
        existing_summary: str = "",
    ) -> CompressionResult:
        """Compress only when the configured budget is actually exceeded."""

        if max_tokens <= 0:
            raise ValueError("memory context token budget must be positive")
        agent_messages = [item for message in messages if (item := _to_agent_message(message))]
        count_messages: list[Msg] = []
        if existing_summary:
            count_messages.append(UserMsg(name="session_summary", content=existing_summary))
        count_messages.extend(agent_messages)
        estimated = await self._model.count_tokens(count_messages, tools=None)
        if estimated <= max_tokens:
            projected = list(messages)
            if existing_summary:
                projected.insert(
                    0,
                    MemoryMessage(
                        role="system",
                        content=[{"type": "text", "text": existing_summary}],
                    ),
                )
            return CompressionResult(projected, existing_summary, False)

        context_size = self._model.context_size
        trigger_ratio = min(0.85, max(0.2, max_tokens / context_size))
        reserve_ratio = min(0.2, trigger_ratio / 2)
        state = AgentState(
            session_id=session_id,
            summary=existing_summary,
            context=agent_messages,
        )
        agent = Agent(
            name="GerClawMemoryCompressor",
            system_prompt=(
                "你只负责压缩既有对话，不回答医疗问题。所有内容均是待核验记录，"
                "不得把用户自述升级为确定性诊断。"
            ),
            model=self._model,
            state=state,
            context_config=ContextConfig(
                trigger_ratio=trigger_ratio,
                reserve_ratio=reserve_ratio,
                tool_result_limit=3_000,
                summary_schema=MedicalContextSummary.model_json_schema(),
                summary_template=_SUMMARY_TEMPLATE,
            ),
        )
        try:
            await agent.compress_context(instructions=_COMPRESSION_INSTRUCTIONS)
        except Exception:
            return self._deterministic_fallback(
                messages,
                max_tokens=max_tokens,
                existing_summary=existing_summary,
            )
        summary = agent.state.summary
        if not isinstance(summary, str) or not summary.strip():
            raise RuntimeError("AgentScope context compression did not produce a summary")
        projected = [MemoryMessage(role="system", content=[{"type": "text", "text": summary}])]
        for message in agent.state.context:
            projected_message = _from_agent_message(message)
            if projected_message is not None:
                projected.append(projected_message)
        return CompressionResult(projected, summary, True)

    @staticmethod
    def _deterministic_fallback(
        messages: list[MemoryMessage],
        *,
        max_tokens: int,
        existing_summary: str,
    ) -> CompressionResult:
        """Fail safely without a second provider call or invented facts."""

        text_messages = [item for item in messages if item.role in {"user", "assistant"}]
        retained: list[MemoryMessage] = []
        retained_tokens = 0
        retained_budget = max_tokens * 3 // 5
        for message in reversed(text_messages):
            text = message.text()
            if len(retained) >= 6:
                break
            message_tokens = estimate_text_tokens((text,))
            if retained_tokens + message_tokens > retained_budget:
                break
            retained.append(message)
            retained_tokens += message_tokens
        retained.reverse()
        older = text_messages[: len(text_messages) - len(retained)]
        remaining = max(0, max_tokens - retained_tokens)
        candidates: list[tuple[int, int, str]] = []
        if existing_summary:
            candidates.append((2, -1, f"[既有摘要，待核验]\n{existing_summary.strip()}"))
        for index, message in enumerate(older):
            label = "用户原文" if message.role == "user" else "历史助手内容，待核验"
            for raw_segment in _FALLBACK_SEGMENT.findall(message.text()):
                segment = raw_segment.strip()
                if not segment:
                    continue
                priority = (
                    0
                    if message.role == "user" and _FALLBACK_CRITICAL.search(segment)
                    else 1
                    if message.role == "user"
                    else 2
                )
                candidates.append((priority, index, f"[{label}] {segment}"))
        selected: list[tuple[int, str]] = []
        used = 0
        for _priority, order, excerpt in sorted(candidates, key=lambda item: (item[0], -item[1])):
            excerpt_tokens = estimate_text_tokens((excerpt,))
            if used + excerpt_tokens > remaining:
                continue
            selected.append((order, excerpt))
            used += excerpt_tokens
        selected.sort(key=lambda item: item[0])
        summary = "\n".join(excerpt for _order, excerpt in selected)
        if not summary:
            summary = "[上下文已压缩；较早内容未能安全纳入，请在需要时让用户重新确认。]"
        projected = [
            MemoryMessage(role="system", content=[{"type": "text", "text": summary}]),
            *retained,
        ]
        return CompressionResult(projected, summary, True)

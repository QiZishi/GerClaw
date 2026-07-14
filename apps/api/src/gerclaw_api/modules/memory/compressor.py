"""AgentScope ContextConfig compression with medical-critical preservation."""

# ruff: noqa: RUF001 -- Chinese medical prompts intentionally use CJK punctuation.

from __future__ import annotations

from dataclasses import dataclass

from agentscope.agent import Agent, ContextConfig
from agentscope.message import AssistantMsg, HintBlock, Msg, UserMsg
from agentscope.model import ChatModelBase
from agentscope.state import AgentState
from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.modules.memory.protocols import MemoryMessage

_COMPRESSION_INSTRUCTIONS = HintBlock(
    hint=(
        "压缩时必须保留：用户明确自述的全部过敏史、当前和已停用药物及剂量、"
        "慢病来源状态、生命体征数值与时间、跌倒/急诊/自伤等红旗事件、"
        "仍待确认的问题。禁止把症状升级成诊断，禁止编造未出现的事实。"
    ),
    source="system",
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
        await agent.compress_context(instructions=_COMPRESSION_INSTRUCTIONS)
        summary = agent.state.summary
        if not isinstance(summary, str) or not summary.strip():
            raise RuntimeError("AgentScope context compression did not produce a summary")
        projected = [MemoryMessage(role="system", content=[{"type": "text", "text": summary}])]
        for message in agent.state.context:
            projected_message = _from_agent_message(message)
            if projected_message is not None:
                projected.append(projected_message)
        return CompressionResult(projected, summary, True)

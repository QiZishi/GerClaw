"""AgentScope ReAct Harness event, evidence, and safety behavior tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
from agentscope.credential import CredentialBase
from agentscope.message import Msg, TextBlock, ToolCallBlock
from agentscope.model import ChatModelBase, ChatResponse, ChatUsage
from agentscope.tool import ToolChoice

from gerclaw_api.config import Settings
from gerclaw_api.modules.agent_harness.harness import (
    AgentHarnessError,
    ProductionAgentHarness,
    UnsupportedAgentContextError,
    _CanonicalTextStream,
)
from gerclaw_api.modules.agent_harness.protocols import ConversationHistoryMessage, StreamEvent
from gerclaw_api.modules.agent_harness.safety import (
    MEDICAL_DISCLAIMER,
    EvidenceUnavailableError,
)
from gerclaw_api.modules.contracts import ExecutionContext
from gerclaw_api.modules.rag.protocols import RetrievalResult
from gerclaw_api.services.model_router import FailoverChatModel


class _HarnessModel(ChatModelBase):
    class Parameters(ChatModelBase.Parameters):
        pass

    def __init__(
        self,
        *,
        use_tool: bool = False,
        text: str = "",
        final_only: bool = False,
        final_text: str | None = None,
    ) -> None:
        self.use_tool = use_tool
        self.text = text or "您已经确诊为高血压。建议请医生复核。"
        self.final_only = final_only
        self.final_text = final_text
        self.calls = 0
        super().__init__(
            credential=CredentialBase(name="test"),
            model="harness-test-model",
            parameters=self.Parameters(),
            stream=True,
            max_retries=0,
            context_size=32_768,
        )

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        del model_name, messages, tools, tool_choice, kwargs
        self.calls += 1
        if self.use_tool and self.calls == 1:
            return ChatResponse(
                content=[
                    ToolCallBlock(
                        id="tool_call_001",
                        name="search_knowledge",
                        input='{"query":"老年跌倒预防"}',
                    )
                ],
                is_last=True,
                usage=ChatUsage(input_tokens=10, output_tokens=3, time=0.01),
            )

        async def stream() -> AsyncGenerator[ChatResponse, None]:
            midpoint = max(1, len(self.text) // 2)
            chunks = (self.text[:midpoint], self.text[midpoint:])
            if not self.final_only:
                for text in chunks:
                    if text:
                        yield ChatResponse(content=[TextBlock(text=text)], is_last=False)
            yield ChatResponse(
                content=[TextBlock(text=self.final_text or self.text)],
                is_last=True,
                usage=ChatUsage(input_tokens=12, output_tokens=8, time=0.01),
            )

        return stream()


class _HarnessRAG:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.calls: list[str] = []

    async def retrieve(
        self, query: str, top_k: int = 5, filters: object | None = None
    ) -> list[RetrievalResult]:
        del top_k, filters
        self.calls.append(query)
        return self.results


def _evidence() -> RetrievalResult:
    return RetrievalResult(
        content="老年高血压管理需结合血压测量、合并症与用药情况综合评估。",
        source="高血压/老年高血压指南.md",
        score=0.91,
        metadata={
            "chunk_id": "chunk-evidence-001",
            "document_id": "document-evidence-001",
            "title": "老年高血压管理指南",
            "chapter": "综合评估",
            "chunk_index": 2,
            "total_chunks": 10,
        },
    )


def _execution() -> ExecutionContext:
    return ExecutionContext(
        request_id="request_abcdefgh",
        trace_id="trace_abcdefgh",
        tenant_id="tenant_public0001",
        actor_id="usr_patient00000001",
        session_id="108815d7-05bf-4c2a-a977-cd034f390fab",
    )


def _harness(
    settings: Settings,
    *,
    model: _HarnessModel,
    rag: _HarnessRAG,
    history: list[ConversationHistoryMessage] | None = None,
) -> ProductionAgentHarness:
    return ProductionAgentHarness(
        settings=settings,
        model=cast(FailoverChatModel, model),
        rag_module=cast(Any, rag),
        execution=_execution(),
        history=history or [],
    )


def test_canonical_text_stream_strips_only_outer_whitespace() -> None:
    stream = _CanonicalTextStream()

    assert stream.feed("") == ""
    assert stream.feed("  第一段 ") == "第一段"
    assert stream.pending_whitespace == " "
    assert stream.feed("第二段  ") == " 第二段"
    assert stream.pending_whitespace == "  "
    stream.finish()
    assert stream.pending_whitespace == ""


@pytest.mark.asyncio
async def test_medical_harness_streams_sanitized_cited_response(
    unit_settings: Settings,
) -> None:
    model = _HarnessModel()
    rag = _HarnessRAG([_evidence()])
    harness = _harness(
        unit_settings,
        model=model,
        rag=rag,
        history=[ConversationHistoryMessage(role="user", text="此前血压偏高")],
    )
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )
    events: list[StreamEvent] = []
    response = await harness.process_message(
        "老年高血压需要注意什么？",
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        context,
        events.append,
    )
    event_types = [event.event_type for event in events]
    assert event_types[0] == "agent_start"
    assert "reasoning_summary" in event_types
    assert event_types[-1] == "done"
    assert "确诊" not in response.text
    assert "进一步评估" in response.text
    assert response.safety.deterministic_diagnosis_blocked
    assert response.text.endswith(MEDICAL_DISCLAIMER)
    assert response.citations[0].source_id == "chunk-evidence-001"
    streamed = "".join(
        str(event.data["content"]) for event in events if event.event_type == "text_delta"
    )
    assert streamed == response.text
    assert rag.calls == ["老年高血压需要注意什么？"]


@pytest.mark.asyncio
async def test_agentic_search_tool_projects_tool_events(unit_settings: Settings) -> None:
    model = _HarnessModel(use_tool=True, text="根据证据，建议评估跌倒风险。")
    rag = _HarnessRAG([_evidence()])
    harness = _harness(unit_settings, model=model, rag=rag)
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )
    events: list[StreamEvent] = []
    response = await harness.process_message(
        "怎样预防老年人跌倒？",
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        context,
        events.append,
    )
    assert model.calls == 2
    assert len(rag.calls) == 2
    assert [event.event_type for event in events].count("tool_call") == 1
    assert [event.event_type for event in events].count("tool_result") == 1
    assert len(response.citations) == 1


@pytest.mark.asyncio
async def test_final_only_provider_text_is_safely_recovered_from_agent_state(
    unit_settings: Settings,
) -> None:
    model = _HarnessModel(
        use_tool=True,
        final_only=True,
        text="您患有高血压。建议由医生结合检查进一步评估。",
    )
    harness = _harness(unit_settings, model=model, rag=_HarnessRAG([_evidence()]))
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )
    events: list[StreamEvent] = []

    response = await harness.process_message(
        "老年高血压怎样管理？",
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        context,
        events.append,
    )

    streamed = "".join(
        str(event.data["content"]) for event in events if event.event_type == "text_delta"
    )
    assert model.calls == 2
    assert streamed == response.text
    assert "您患有" not in response.text
    assert response.safety.deterministic_diagnosis_blocked


@pytest.mark.asyncio
async def test_final_only_outer_whitespace_is_canonical_in_sse_and_done(
    unit_settings: Settings,
) -> None:
    model = _HarnessModel(
        final_only=True,
        text="  \n您患有高血压。建议请医生复核。\n  ",
    )
    harness = _harness(unit_settings, model=model, rag=_HarnessRAG([_evidence()]))
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )
    events: list[StreamEvent] = []

    response = await harness.process_message(
        "老年高血压怎样管理？",
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        context,
        events.append,
    )

    streamed = "".join(
        str(event.data["content"]) for event in events if event.event_type == "text_delta"
    )
    assert streamed == response.text
    assert response.text.startswith("您可能存在高血压")
    assert "您患有" not in response.text


@pytest.mark.asyncio
async def test_final_state_mismatch_fails_closed(unit_settings: Settings) -> None:
    model = _HarnessModel(text="公开流文本。", final_text="不一致的最终文本。")
    harness = _harness(unit_settings, model=model, rag=_HarnessRAG([_evidence()]))
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )

    with pytest.raises(AgentHarnessError, match="did not match"):
        await harness.process_message(
            "老年健康管理建议",
            "108815d7-05bf-4c2a-a977-cd034f390fab",
            context,
            lambda _event: None,
        )


@pytest.mark.asyncio
async def test_final_state_whitespace_only_difference_uses_public_stream(
    unit_settings: Settings,
) -> None:
    model = _HarnessModel(
        text="第一段。第二段。",
        final_text="第一段。\n\n第二段。",
    )
    harness = _harness(unit_settings, model=model, rag=_HarnessRAG([_evidence()]))
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )
    events: list[StreamEvent] = []

    response = await harness.process_message(
        "老年健康管理建议",
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        context,
        events.append,
    )

    streamed = "".join(
        str(event.data["content"]) for event in events if event.event_type == "text_delta"
    )
    assert streamed == response.text
    assert response.text.startswith("第一段。第二段。")


@pytest.mark.asyncio
async def test_final_only_provider_output_still_obeys_character_limit(
    unit_settings: Settings,
) -> None:
    constrained = unit_settings.model_copy(update={"agent_max_output_characters": 1_000})
    model = _HarnessModel(text="建议。" * 400, final_only=True)
    harness = _harness(constrained, model=model, rag=_HarnessRAG([_evidence()]))
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )

    with pytest.raises(AgentHarnessError, match="output exceeded"):
        await harness.process_message(
            "老年健康建议",
            "108815d7-05bf-4c2a-a977-cd034f390fab",
            context,
            lambda _event: None,
        )


@pytest.mark.asyncio
async def test_non_medical_small_talk_bypasses_evidence(unit_settings: Settings) -> None:
    model = _HarnessModel(text="您好，很高兴为您服务。")
    rag = _HarnessRAG([])
    harness = _harness(unit_settings, model=model, rag=rag)
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )
    response = await harness.process_message(
        "您好！",
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        context,
        lambda _event: None,
    )
    assert not response.medical_content
    assert response.citations == []
    assert rag.calls == []


@pytest.mark.asyncio
async def test_high_risk_notice_is_first_public_text(unit_settings: Settings) -> None:
    model = _HarnessModel(text="请立即就医。")
    rag = _HarnessRAG([_evidence()])
    harness = _harness(unit_settings, model=model, rag=rag)
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )
    events: list[StreamEvent] = []
    response = await harness.process_message(
        "老人突然胸痛并且呼吸困难",
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        context,
        events.append,
    )
    first_text = next(event for event in events if event.event_type == "text_delta")
    assert "120" in str(first_text.data["content"])
    assert "立即" in response.text
    assert "high_risk_escalation_applied" in response.safety.notices


@pytest.mark.asyncio
async def test_medical_request_without_evidence_fails_closed(
    unit_settings: Settings,
) -> None:
    harness = _harness(unit_settings, model=_HarnessModel(), rag=_HarnessRAG([]))
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )
    with pytest.raises(EvidenceUnavailableError):
        await harness.process_message(
            "这个药安全吗？",
            "108815d7-05bf-4c2a-a977-cd034f390fab",
            context,
            lambda _event: None,
        )


@pytest.mark.asyncio
async def test_non_projectable_evidence_fails_before_model_or_medical_text(
    unit_settings: Settings,
) -> None:
    invalid = RetrievalResult(
        content="没有可追溯元数据的内容",
        source="unknown",
        score=0.9,
        metadata={"chunk_id": 123},
    )
    model = _HarnessModel(text="您患有冠心病。")
    harness = _harness(unit_settings, model=model, rag=_HarnessRAG([invalid]))
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )
    events: list[StreamEvent] = []
    with pytest.raises(EvidenceUnavailableError):
        await harness.process_message(
            "请判断老人是不是冠心病",
            "108815d7-05bf-4c2a-a977-cd034f390fab",
            context,
            events.append,
        )

    assert model.calls == 0
    assert all(event.event_type != "text_delta" for event in events)
    assert all(event.event_type != "done" for event in events)


@pytest.mark.asyncio
async def test_adversarial_diagnosis_phrases_are_rewritten_and_audited(
    unit_settings: Settings,
) -> None:
    unsafe = "您患有冠心病。这是心力衰竭。诊断是高血压。明确诊断为糖尿病。"
    harness = _harness(
        unit_settings,
        model=_HarnessModel(text=unsafe),
        rag=_HarnessRAG([_evidence()]),
    )
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )
    events: list[StreamEvent] = []
    response = await harness.process_message(
        "老人多病共存应该如何评估？",
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        context,
        events.append,
    )

    assert all(phrase not in response.text for phrase in ("您患有", "这是", "诊断是", "明确诊断"))
    assert "明需" not in response.text
    assert response.safety.deterministic_diagnosis_blocked
    streamed = "".join(
        str(event.data["content"]) for event in events if event.event_type == "text_delta"
    )
    assert streamed == response.text


@pytest.mark.asyncio
async def test_context_rejects_unimplemented_skill_and_identity(
    unit_settings: Settings,
) -> None:
    harness = _harness(unit_settings, model=_HarnessModel(), rag=_HarnessRAG([]))
    with pytest.raises(UnsupportedAgentContextError):
        await harness.assemble_context(
            "108815d7-05bf-4c2a-a977-cd034f390fab",
            "usr_patient00000001",
            ["prescription"],
            [],
        )
    with pytest.raises(ValueError, match="identity"):
        await harness.assemble_context(
            "108815d7-05bf-4c2a-a977-cd034f390fab",
            "usr_other0000000001",
            [],
            [],
        )


@pytest.mark.asyncio
async def test_output_limit_fails_instead_of_persisting_truncated_success(
    unit_settings: Settings,
) -> None:
    constrained = unit_settings.model_copy(update={"agent_max_output_characters": 1_000})
    harness = _harness(
        constrained,
        model=_HarnessModel(text="建议。" * 400),
        rag=_HarnessRAG([_evidence()]),
    )
    context = await harness.assemble_context(
        "108815d7-05bf-4c2a-a977-cd034f390fab",
        "usr_patient00000001",
        [],
        [],
    )
    with pytest.raises(AgentHarnessError, match="output exceeded"):
        await harness.process_message(
            "老年健康建议",
            "108815d7-05bf-4c2a-a977-cd034f390fab",
            context,
            lambda _event: None,
        )

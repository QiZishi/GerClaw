# ruff: noqa: RUF001
"""Ordered AgentScope model failover and partial-stream fencing tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from unittest.mock import patch

import pytest
from agentscope.credential import CredentialBase
from agentscope.message import Base64Source, DataBlock, Msg, TextBlock, ThinkingBlock, UserMsg
from agentscope.model import ChatModelBase, ChatResponse, ChatUsage, StructuredResponse
from agentscope.tool import ToolChoice
from pydantic import BaseModel

from gerclaw_api.config import AgentModelConfig
from gerclaw_api.services import model_router
from gerclaw_api.services.model_factory import build_agentscope_model, close_agentscope_model
from gerclaw_api.services.model_router import (
    FailoverChatModel,
    ModelCapabilityUnavailableError,
    ModelChainExhaustedError,
    ModelPromptPrivacyError,
    PartialModelStreamError,
    bind_model_prompt_egress_audit,
    capture_model_attempts,
    redact_model_messages,
)


@dataclass(slots=True)
class _Action:
    kind: str
    text: str = ""


class _ScriptedModel(ChatModelBase):
    class Parameters(ChatModelBase.Parameters):
        pass

    def __init__(self, name: str, actions: list[_Action]) -> None:
        self.actions = actions
        self.calls = 0
        self.last_messages: list[Msg] = []
        super().__init__(
            credential=CredentialBase(name="test"),
            model=name,
            parameters=self.Parameters(),
            stream=True,
            max_retries=0,
        )

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        del model_name, tools, tool_choice, kwargs
        self.calls += 1
        self.last_messages = messages
        actions = list(self.actions)
        if actions and actions[0].kind == "raise_open":
            raise RuntimeError("provider detail must not escape")

        async def stream() -> AsyncGenerator[ChatResponse, None]:
            accumulated = ""
            for action in actions:
                if action.kind == "sleep":
                    await asyncio.sleep(float(action.text))
                elif action.kind == "thinking":
                    yield ChatResponse(content=[ThinkingBlock(thinking=action.text)], is_last=False)
                elif action.kind == "text":
                    accumulated += action.text
                    yield ChatResponse(content=[TextBlock(text=action.text)], is_last=False)
                elif action.kind == "raise_stream":
                    raise RuntimeError("stream transport failed")
            yield ChatResponse(
                content=[TextBlock(text=accumulated)],
                is_last=True,
                usage=ChatUsage(input_tokens=3, output_tokens=2, time=0.01),
            )

        return stream()


class _StructuredScriptedModel(_ScriptedModel):
    """A provider double whose structured boundary can fail independently."""

    def __init__(self, name: str, actions: list[_Action]) -> None:
        super().__init__(name, actions)
        self.structured_tool_choices: list[ToolChoice | None] = []
        self.structured_messages: list[list[Msg]] = []
        self.structured_models: list[type[BaseModel] | dict[str, Any]] = []

    async def generate_structured_output(
        self,
        messages: list[Msg],
        structured_model: type[BaseModel] | dict[str, Any],
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> StructuredResponse:
        del kwargs
        self.calls += 1
        self.structured_messages.append(messages)
        self.structured_models.append(structured_model)
        self.structured_tool_choices.append(tool_choice)
        if self.actions and self.actions[0].kind == "raise_structured":
            raise ValueError("provider returned a non-tool response")
        return StructuredResponse(content={"result": self.actions[0].text})


class _PromptAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, object]] = []

    async def prepare(self, *, preference: str, decision: object) -> object:
        handle = object()
        self.events.append(("prepared", preference, decision))
        return handle

    async def finish(self, handle: object, *, outcome: str) -> None:
        self.events.append((outcome, "", handle))


def _router(
    models: Sequence[_ScriptedModel],
    *,
    timeout_seconds: float = 30.0,
    protocols: tuple[
        Literal["openai", "dashscope", "anthropic"],
        Literal["openai", "dashscope", "anthropic"],
        Literal["openai", "dashscope", "anthropic"],
    ] = ("openai", "openai", "openai"),
    model_names: tuple[str, str, str] = (
        "primary-model",
        "backup1-model",
        "backup2-model",
    ),
    supports_image_input: tuple[bool, bool, bool] = (True, True, True),
    supports_tool_calling: tuple[bool, bool, bool] = (True, True, True),
    supports_structured_output: tuple[bool, bool, bool] = (True, True, True),
) -> FailoverChatModel:
    configs = tuple(
        AgentModelConfig(
            url=f"https://{preference}.example/v1",
            api_key=f"tests-{preference}-secret",
            model_name=model_names[index],
            protocol=protocols[index],
            preference=preference,
            timeout_seconds=timeout_seconds,
            supports_image_input=supports_image_input[index],
            supports_tool_calling=supports_tool_calling[index],
            supports_structured_output=supports_structured_output[index],
        )
        for index, preference in enumerate(("primary", "backup1", "backup2"))
    )
    with patch.object(model_router, "build_agentscope_model", side_effect=models):
        return FailoverChatModel(configs)


def test_router_identity_uses_configured_primary_model() -> None:
    models = [
        _ScriptedModel("configured-primary-model", []),
        _ScriptedModel("configured-backup1-model", []),
        _ScriptedModel("configured-backup2-model", []),
    ]

    router = _router(models)

    assert router.model == "configured-primary-model"


async def _consume(router: FailoverChatModel) -> str:
    return await _consume_with_messages(router, [UserMsg(name="user", content="hello")])


async def _consume_with_messages(router: FailoverChatModel, messages: list[Msg]) -> str:
    response = await router(messages)
    assert not isinstance(response, ChatResponse)
    text = ""
    async for chunk in response:
        for block in chunk.content:
            if isinstance(block, TextBlock) and not chunk.is_last:
                text += block.text
    return text


@pytest.mark.asyncio
async def test_primary_model_success_does_not_touch_backups() -> None:
    models = [
        _ScriptedModel("primary", [_Action("text", "主模型回复")]),
        _ScriptedModel("backup1", [_Action("text", "unused")]),
        _ScriptedModel("backup2", [_Action("text", "unused")]),
    ]
    router = _router(models)
    with capture_model_attempts() as attempts:
        assert await _consume(router) == "主模型回复"
    assert [model.calls for model in models] == [1, 0, 0]
    assert [(item.preference, item.outcome) for item in attempts] == [
        ("primary", "started"),
        ("primary", "succeeded"),
    ]


@pytest.mark.asyncio
async def test_open_failure_falls_over_in_order() -> None:
    models = [
        _ScriptedModel("primary", [_Action("raise_open")]),
        _ScriptedModel("backup1", [_Action("text", "备用成功")]),
        _ScriptedModel("backup2", [_Action("text", "unused")]),
    ]
    router = _router(models)
    with capture_model_attempts() as attempts:
        assert await _consume(router) == "备用成功"
    assert [model.calls for model in models] == [1, 1, 0]
    assert [item.outcome for item in attempts] == [
        "started",
        "failed",
        "started",
        "succeeded",
    ]


@pytest.mark.asyncio
async def test_image_request_skips_models_that_do_not_declare_vision_support() -> None:
    models = [
        _ScriptedModel("primary", [_Action("text", "must not run")]),
        _ScriptedModel("backup1", [_Action("text", "看到了图片")]),
        _ScriptedModel("backup2", [_Action("text", "must not run")]),
    ]
    router = _router(models, supports_image_input=(False, True, False))
    message = UserMsg(
        name="user",
        content=[
            DataBlock(source=Base64Source(media_type="image/png", data="aGVsbG8=")),
            TextBlock(text="请解读这张图片"),
        ],
    )

    with capture_model_attempts() as attempts:
        assert await _consume_with_messages(router, [message]) == "看到了图片"

    assert [model.calls for model in models] == [0, 1, 0]
    assert [(item.preference, item.error_code) for item in attempts] == [
        ("primary", "MODEL_IMAGE_INPUT_UNSUPPORTED"),
        ("backup2", "MODEL_IMAGE_INPUT_UNSUPPORTED"),
        ("backup1", None),
        ("backup1", None),
    ]
    assert {item.capability_version for item in attempts} == {"model-capabilities-v1"}


@pytest.mark.asyncio
async def test_request_without_a_declared_capable_model_fails_before_provider_egress() -> None:
    models = [
        _ScriptedModel("primary", [_Action("text", "must not run")]),
        _ScriptedModel("backup1", [_Action("text", "must not run")]),
        _ScriptedModel("backup2", [_Action("text", "must not run")]),
    ]
    router = _router(models, supports_structured_output=(False, False, False))

    with capture_model_attempts() as attempts, pytest.raises(ModelCapabilityUnavailableError):
        await router.generate_structured_output(
            [UserMsg(name="user", content="生成严格 JSON")],
            {"type": "object", "properties": {"result": {"type": "string"}}},
        )

    assert [model.calls for model in models] == [0, 0, 0]
    assert [item.error_code for item in attempts] == [
        "MODEL_STRUCTURED_OUTPUT_UNSUPPORTED",
        "MODEL_STRUCTURED_OUTPUT_UNSUPPORTED",
        "MODEL_STRUCTURED_OUTPUT_UNSUPPORTED",
    ]


@pytest.mark.asyncio
async def test_structured_output_fails_over_after_provider_schema_failure() -> None:
    models = [
        _StructuredScriptedModel("primary", [_Action("raise_structured")]),
        _StructuredScriptedModel("backup1", [_Action("structured", "fallback")]),
        _StructuredScriptedModel("backup2", [_Action("structured", "unused")]),
    ]
    router = _router(models, protocols=("openai", "dashscope", "openai"))

    with capture_model_attempts() as attempts:
        response = await router.generate_structured_output(
            [UserMsg(name="user", content="hello")],
            {"type": "object", "properties": {"result": {"type": "string"}}},
        )

    assert response.content == {"result": "fallback"}
    assert [model.calls for model in models] == [1, 1, 0]
    assert [(item.preference, item.outcome, item.error_code) for item in attempts] == [
        ("primary", "started", None),
        ("primary", "failed", "MODEL_INVALID_STRUCTURED_OUTPUT"),
        ("backup1", "started", None),
        ("backup1", "succeeded", None),
    ]
    assert models[1].structured_tool_choices[0] == ToolChoice(mode="auto")


@pytest.mark.asyncio
async def test_structured_failover_replays_full_context_and_same_schema_to_backup() -> None:
    """A backup must receive task context, not an unprompted schema request."""

    models = [
        _StructuredScriptedModel("primary", [_Action("raise_structured")]),
        _StructuredScriptedModel("backup1", [_Action("structured", "fallback")]),
        _StructuredScriptedModel("backup2", [_Action("structured", "unused")]),
    ]
    router = _router(models)
    messages = [
        UserMsg(name="user", content="患者主诉：近三日头晕"),
        UserMsg(name="user", content="任务：仅输出结构化分诊草案"),
    ]
    schema = {"type": "object", "properties": {"result": {"type": "string"}}}

    await router.generate_structured_output(messages, schema)

    assert models[0].structured_messages == models[1].structured_messages
    assert models[1].structured_messages[0][1].content[0].text == "任务：仅输出结构化分诊草案"
    assert models[0].structured_models == models[1].structured_models == [schema]


@pytest.mark.asyncio
async def test_structured_output_uses_provider_agnostic_auto_tool_choice() -> None:
    models = [
        _StructuredScriptedModel("primary", [_Action("structured", "primary")]),
        _StructuredScriptedModel("backup1", [_Action("structured", "unused")]),
        _StructuredScriptedModel("backup2", [_Action("structured", "unused")]),
    ]
    router = _router(models)

    await router.generate_structured_output(
        [UserMsg(name="user", content="hello")],
        {"type": "object", "properties": {"result": {"type": "string"}}},
        tool_choice=ToolChoice(mode="required"),
    )

    assert models[0].structured_tool_choices == [ToolChoice(mode="auto")]


@pytest.mark.asyncio
async def test_model_provider_attempts_have_redacted_audit_lifecycle() -> None:
    models = [
        _ScriptedModel("primary", [_Action("raise_open")]),
        _ScriptedModel("backup1", [_Action("text", "安全回复")]),
        _ScriptedModel("backup2", [_Action("text", "unused")]),
    ]
    audit = _PromptAudit()
    router = _router(models)

    with bind_model_prompt_egress_audit(audit):
        assert (
            await _consume_with_messages(
                router, [UserMsg(name="user", content="患者姓名：李雷，电话 13800138000")]
            )
            == "安全回复"
        )

    assert [(state, preference) for state, preference, _ in audit.events] == [
        ("prepared", "primary"),
        ("failed", ""),
        ("prepared", "backup1"),
        ("succeeded", ""),
    ]
    decision = audit.events[0][2]
    assert decision.text == "[MODEL_PROMPT_REDACTED]"  # type: ignore[union-attr]
    assert "李雷" not in repr(decision)


@pytest.mark.asyncio
async def test_hidden_thinking_can_fail_over_before_visible_output() -> None:
    models = [
        _ScriptedModel("primary", [_Action("thinking", "private"), _Action("raise_stream")]),
        _ScriptedModel("backup1", [_Action("text", "安全重试")]),
        _ScriptedModel("backup2", [_Action("text", "unused")]),
    ]
    router = _router(models)
    assert await _consume(router) == "安全重试"
    assert [model.calls for model in models] == [1, 1, 0]


@pytest.mark.asyncio
async def test_thinking_only_completion_falls_over_to_public_answer() -> None:
    models = [
        _ScriptedModel("primary", [_Action("thinking", "private only")]),
        _ScriptedModel("backup1", [_Action("text", "备用公开回复")]),
        _ScriptedModel("backup2", [_Action("text", "unused")]),
    ]
    router = _router(models)
    with capture_model_attempts() as attempts:
        assert await _consume(router) == "备用公开回复"
    assert [model.calls for model in models] == [1, 1, 0]
    assert [(item.outcome, item.error_code) for item in attempts] == [
        ("started", None),
        ("failed", "MODEL_EMPTY_RESPONSE"),
        ("started", None),
        ("succeeded", None),
    ]


@pytest.mark.asyncio
async def test_whitespace_only_completion_falls_over_to_public_answer() -> None:
    models = [
        _ScriptedModel("primary", [_Action("text", "  \n")]),
        _ScriptedModel("backup1", [_Action("text", "备用公开回复")]),
        _ScriptedModel("backup2", [_Action("text", "unused")]),
    ]
    router = _router(models)
    with capture_model_attempts() as attempts:
        assert await _consume(router) == "备用公开回复"
    assert [model.calls for model in models] == [1, 1, 0]
    assert [(item.outcome, item.error_code) for item in attempts] == [
        ("started", None),
        ("failed", "MODEL_EMPTY_RESPONSE"),
        ("started", None),
        ("succeeded", None),
    ]


@pytest.mark.asyncio
async def test_partial_visible_stream_fails_closed_without_replay() -> None:
    models = [
        _ScriptedModel("primary", [_Action("text", "已经输出"), _Action("raise_stream")]),
        _ScriptedModel("backup1", [_Action("text", "must-not-run")]),
        _ScriptedModel("backup2", [_Action("text", "must-not-run")]),
    ]
    router = _router(models)
    with pytest.raises(PartialModelStreamError):
        await _consume(router)
    assert [model.calls for model in models] == [1, 0, 0]


@pytest.mark.asyncio
async def test_total_stream_deadline_falls_over_before_visible_output() -> None:
    models = [
        _ScriptedModel("primary", [_Action("sleep", "0.05")]),
        _ScriptedModel("backup1", [_Action("text", "限时备用成功")]),
        _ScriptedModel("backup2", [_Action("text", "unused")]),
    ]
    router = _router(models, timeout_seconds=0.01)
    with capture_model_attempts() as attempts:
        assert await _consume(router) == "限时备用成功"
    assert [(item.preference, item.outcome, item.error_code) for item in attempts] == [
        ("primary", "started", None),
        ("primary", "failed", "MODEL_TIMEOUT"),
        ("backup1", "started", None),
        ("backup1", "succeeded", None),
    ]


@pytest.mark.asyncio
async def test_total_stream_deadline_after_visible_output_fails_closed() -> None:
    models = [
        _ScriptedModel(
            "primary",
            [_Action("text", "已经输出"), _Action("sleep", "0.05")],
        ),
        _ScriptedModel("backup1", [_Action("text", "must-not-run")]),
        _ScriptedModel("backup2", [_Action("text", "must-not-run")]),
    ]
    router = _router(models, timeout_seconds=0.01)
    with pytest.raises(PartialModelStreamError):
        await _consume(router)
    assert [model.calls for model in models] == [1, 0, 0]


@pytest.mark.asyncio
async def test_all_model_failures_raise_safe_chain_error() -> None:
    models = [
        _ScriptedModel("primary", [_Action("raise_open")]),
        _ScriptedModel("backup1", [_Action("raise_open")]),
        _ScriptedModel("backup2", [_Action("raise_open")]),
    ]
    router = _router(models)
    with pytest.raises(ModelChainExhaustedError, match="configured model services"):
        await _consume(router)
    assert [model.calls for model in models] == [1, 1, 1]


@pytest.mark.asyncio
async def test_factory_owned_http_client_closes_idempotently() -> None:
    config = AgentModelConfig(
        url="https://model.example/v1",
        api_key="tests-model-secret",
        model_name="test-model",
        protocol="openai",
        preference="primary",
    )
    model = build_agentscope_model(config)
    client = model._gerclaw_owned_http_client

    assert not client.is_closed
    assert model.parameters.max_tokens == 32_768
    await close_agentscope_model(model)
    assert client.is_closed
    await close_agentscope_model(model)


@pytest.mark.asyncio
async def test_router_redacts_provider_bound_prompt_without_mutating_local_message() -> None:
    model = _ScriptedModel("primary", [_Action("text", "安全回复")])
    router = _router(
        [
            model,
            _ScriptedModel("backup1", [_Action("text", "unused")]),
            _ScriptedModel("backup2", [_Action("text", "unused")]),
        ]
    )
    original = UserMsg(name="user", content="患者姓名：李雷，电话 13800138000")

    assert await _consume_with_messages(router, [original]) == "安全回复"
    provider_text = model.last_messages[0].get_text_content()
    assert "李雷" not in provider_text
    assert "13800138000" not in provider_text
    assert original.get_text_content() == "患者姓名：李雷，电话 13800138000"


def test_model_prompt_privacy_fails_closed_for_oversized_text() -> None:
    with pytest.raises(ModelPromptPrivacyError):
        redact_model_messages([UserMsg(name="user", content="x" * 100_001)])

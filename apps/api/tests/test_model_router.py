# ruff: noqa: RUF001
"""Ordered AgentScope model failover and partial-stream fencing tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest
from agentscope.credential import CredentialBase
from agentscope.message import Msg, TextBlock, ThinkingBlock, UserMsg
from agentscope.model import ChatModelBase, ChatResponse, ChatUsage
from agentscope.tool import ToolChoice

from gerclaw_api.config import AgentModelConfig
from gerclaw_api.services import model_router
from gerclaw_api.services.model_factory import build_agentscope_model, close_agentscope_model
from gerclaw_api.services.model_router import (
    FailoverChatModel,
    ModelChainExhaustedError,
    ModelPromptPrivacyError,
    PartialModelStreamError,
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


def _router(models: list[_ScriptedModel], *, timeout_seconds: float = 30.0) -> FailoverChatModel:
    configs = tuple(
        AgentModelConfig(
            url=f"https://{preference}.example/v1",
            api_key=f"tests-{preference}-secret",
            model_name=f"{preference}-model",
            protocol="openai",
            preference=preference,
            timeout_seconds=timeout_seconds,
        )
        for preference in ("primary", "backup1", "backup2")
    )
    with patch.object(model_router, "build_agentscope_model", side_effect=models):
        return FailoverChatModel(configs)


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
    assert model.parameters.max_tokens == 1_024
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

"""AgentScope provider selection tests; network behavior lives in external smoke tests."""

import pytest
from agentscope.model import AnthropicChatModel, DashScopeChatModel, OpenAIChatModel

from gerclaw_api.config import AgentModelConfig
from gerclaw_api.services.model_factory import build_agentscope_model, close_agentscope_model


@pytest.mark.parametrize(
    ("protocol", "expected_type"),
    [
        ("openai", OpenAIChatModel),
        ("dashscope", DashScopeChatModel),
        ("anthropic", AnthropicChatModel),
    ],
)
async def test_model_factory_selects_agentscope_provider(
    protocol: str, expected_type: type[object]
) -> None:
    config = AgentModelConfig.model_validate(
        {
            "url": "https://model.example.com/v1",
            "api_key": "secret",
            "model_name": "model-name",
            "protocol": protocol,
            "preference": "primary",
        }
    )

    model = build_agentscope_model(config)
    try:
        assert isinstance(model, expected_type)
    finally:
        await close_agentscope_model(model)

"""AgentScope model construction from validated environment configuration."""

from __future__ import annotations

from agentscope.credential import (
    AnthropicCredential,
    DashScopeCredential,
    OpenAICredential,
)
from agentscope.model import (
    AnthropicChatModel,
    ChatModelBase,
    DashScopeChatModel,
    OpenAIChatModel,
)

from gerclaw_api.config import AgentModelConfig


def build_agentscope_model(config: AgentModelConfig) -> ChatModelBase:
    """Build a streaming AgentScope model without leaking provider details upstream."""

    base_url = str(config.url).rstrip("/")
    if config.protocol == "openai":
        return OpenAIChatModel(
            credential=OpenAICredential(api_key=config.api_key, base_url=base_url),
            model=config.model_name,
            stream=True,
            max_retries=1,
            client_kwargs={"timeout": config.timeout_seconds},
        )
    if config.protocol == "dashscope":
        return DashScopeChatModel(
            credential=DashScopeCredential(api_key=config.api_key, base_url=base_url),
            model=config.model_name,
            stream=True,
            max_retries=1,
            client_kwargs={"timeout": config.timeout_seconds},
        )
    return AnthropicChatModel(
        credential=AnthropicCredential(api_key=config.api_key, base_url=base_url),
        model=config.model_name,
        stream=True,
        max_retries=1,
        client_kwargs={"timeout": config.timeout_seconds},
    )

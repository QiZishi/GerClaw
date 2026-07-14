"""AgentScope model construction from validated environment configuration."""

from __future__ import annotations

import httpx
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

_OWNED_HTTP_CLIENT_ATTRIBUTE = "_gerclaw_owned_http_client"


def build_agentscope_model(config: AgentModelConfig) -> ChatModelBase:
    """Build a streaming AgentScope model without leaking provider details upstream."""

    base_url = str(config.url).rstrip("/")
    http_client = httpx.AsyncClient(timeout=config.timeout_seconds)
    client_kwargs = {
        "timeout": config.timeout_seconds,
        "http_client": http_client,
    }
    if config.protocol == "openai":
        model: ChatModelBase = OpenAIChatModel(
            credential=OpenAICredential(api_key=config.api_key, base_url=base_url),
            model=config.model_name,
            stream=True,
            max_retries=1,
            client_kwargs=client_kwargs,
        )
    elif config.protocol == "dashscope":
        model = DashScopeChatModel(
            credential=DashScopeCredential(api_key=config.api_key, base_url=base_url),
            model=config.model_name,
            stream=True,
            max_retries=1,
            client_kwargs=client_kwargs,
        )
    else:
        model = AnthropicChatModel(
            credential=AnthropicCredential(api_key=config.api_key, base_url=base_url),
            model=config.model_name,
            stream=True,
            max_retries=1,
            client_kwargs=client_kwargs,
        )
    setattr(model, _OWNED_HTTP_CLIENT_ATTRIBUTE, http_client)
    return model


async def close_agentscope_model(model: ChatModelBase) -> None:
    """Close the HTTP client injected into an AgentScope provider adapter."""

    client = getattr(model, _OWNED_HTTP_CLIENT_ATTRIBUTE, None)
    if isinstance(client, httpx.AsyncClient) and not client.is_closed:
        await client.aclose()

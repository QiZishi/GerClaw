"""Validate, persist, and resolve account-scoped Agent model overrides."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr

from gerclaw_api.config import AgentModelConfig, Settings

MODEL_CONFIG_SCHEMA_VERSION = "account-model-override-v1"
SlotPreference = Literal["primary", "backup1", "backup2"]


class AccountModelSlotWrite(BaseModel):
    """A complete override for one model slot; API keys never reappear in reads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    preference: SlotPreference
    url: AnyHttpUrl
    api_key: SecretStr = Field(min_length=1, max_length=2_048)
    model_name: str = Field(min_length=1, max_length=128)
    protocol: Literal["openai", "dashscope", "anthropic"]
    supports_image_input: bool = True
    supports_tool_calling: bool = True
    supports_structured_output: bool = True

    def to_agent_config(self, settings: Settings) -> AgentModelConfig:
        return AgentModelConfig(
            url=self.url,
            api_key=self.api_key,
            model_name=self.model_name,
            protocol=self.protocol,
            preference=self.preference,
            timeout_seconds=settings.agent_model_timeout_seconds,
            max_output_tokens=settings.agent_model_max_output_tokens,
            capability_version=settings.agent_model_capability_version,
            supports_image_input=self.supports_image_input,
            supports_tool_calling=self.supports_tool_calling,
            supports_structured_output=self.supports_structured_output,
        )


class AccountModelSlotRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    preference: SlotPreference
    url: str
    model_name: str
    protocol: Literal["openai", "dashscope", "anthropic"]
    api_key_configured: bool = True
    supports_image_input: bool
    supports_tool_calling: bool
    supports_structured_output: bool


def serialize_slots(slots: tuple[AccountModelSlotWrite, ...]) -> dict[str, Any]:
    """Serialize plaintext only for the encrypted database column, never logs."""

    return {
        "schema_version": MODEL_CONFIG_SCHEMA_VERSION,
        "slots": [
            {
                "preference": slot.preference,
                "url": str(slot.url),
                "api_key": slot.api_key.get_secret_value(),
                "model_name": slot.model_name,
                "protocol": slot.protocol,
                "supports_image_input": slot.supports_image_input,
                "supports_tool_calling": slot.supports_tool_calling,
                "supports_structured_output": slot.supports_structured_output,
            }
            for slot in slots
        ],
    }


def parse_slots(configuration: dict[str, Any]) -> tuple[AccountModelSlotWrite, ...]:
    """Reject corrupted or old encrypted payloads instead of silently using them."""

    if configuration.get("schema_version") != MODEL_CONFIG_SCHEMA_VERSION:
        raise ValueError("account model configuration schema is not supported")
    raw_slots = configuration.get("slots")
    if not isinstance(raw_slots, list) or len(raw_slots) > 3:
        raise ValueError("account model configuration slots are invalid")
    slots = tuple(AccountModelSlotWrite.model_validate(item) for item in raw_slots)
    if len({slot.preference for slot in slots}) != len(slots):
        raise ValueError("account model configuration contains duplicate slots")
    return slots


def read_slots(configuration: dict[str, Any]) -> tuple[AccountModelSlotRead, ...]:
    return tuple(
        AccountModelSlotRead(
            preference=slot.preference,
            url=str(slot.url),
            model_name=slot.model_name,
            protocol=slot.protocol,
            supports_image_input=slot.supports_image_input,
            supports_tool_calling=slot.supports_tool_calling,
            supports_structured_output=slot.supports_structured_output,
        )
        for slot in parse_slots(configuration)
    )


def resolve_effective_configs(
    settings: Settings, configuration: dict[str, Any] | None
) -> tuple[AgentModelConfig, ...]:
    """Overlay complete account slots onto deployment defaults without mutation."""

    effective = {config.preference: config for config in settings.agent_model_configs}
    if configuration is not None:
        effective.update(
            {slot.preference: slot.to_agent_config(settings) for slot in parse_slots(configuration)}
        )
    ordered = tuple(
        effective[name] for name in ("primary", "backup1", "backup2") if name in effective
    )
    if len(ordered) != 3:
        raise ValueError("effective account model chain requires three complete slots")
    return ordered

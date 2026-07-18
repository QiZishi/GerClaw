"""Validate, persist, and resolve account-scoped external service overrides."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr, model_validator

from gerclaw_api.config import AgentModelConfig, Settings

MODEL_CONFIG_SCHEMA_VERSION = "account-model-override-v2"
_LEGACY_MODEL_CONFIG_SCHEMA_VERSION = "account-model-override-v1"
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


class SearchServiceWrite(BaseModel):
    """Optional complete provider pairs for the online-search runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    anysearch_url: AnyHttpUrl | None = None
    anysearch_api_key: SecretStr | None = Field(default=None, max_length=2_048)
    tavily_url: AnyHttpUrl | None = None
    tavily_api_key: SecretStr | None = Field(default=None, max_length=2_048)

    @model_validator(mode="after")
    def complete_provider_pairs(self) -> SearchServiceWrite:
        if (self.anysearch_url is None) != (self.anysearch_api_key is None):
            raise ValueError("AnySearch 服务地址和 API Key 必须同时填写")
        if (self.tavily_url is None) != (self.tavily_api_key is None):
            raise ValueError("Tavily 服务地址和 API Key 必须同时填写")
        return self


class VectorServiceWrite(BaseModel):
    """One OpenAI-compatible endpoint shared by embedding and reranking."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: AnyHttpUrl
    api_key: SecretStr = Field(min_length=1, max_length=2_048)
    embedding_model: str = Field(min_length=1, max_length=128)
    rerank_model: str = Field(min_length=1, max_length=128)


class VoiceServiceWrite(BaseModel):
    """MiMo-compatible ASR/TTS override, kept together to preserve the adapter contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr = Field(min_length=1, max_length=2_048)
    asr_url: AnyHttpUrl
    asr_model: str = Field(min_length=1, max_length=128)
    tts_url: AnyHttpUrl
    tts_model: str = Field(min_length=1, max_length=128)
    tts_voice: str = Field(min_length=1, max_length=64)


class MinerUServiceWrite(BaseModel):
    """MinerU document parsing endpoint and credential."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: AnyHttpUrl
    api_key: SecretStr = Field(min_length=1, max_length=2_048)


class AccountServiceOverridesWrite(BaseModel):
    """Only explicitly completed service groups replace deployment defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    search: SearchServiceWrite | None = None
    vector: VectorServiceWrite | None = None
    voice: VoiceServiceWrite | None = None
    mineru: MinerUServiceWrite | None = None


class SearchServiceRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    anysearch_url: str | None = None
    anysearch_api_key_configured: bool = False
    tavily_url: str | None = None
    tavily_api_key_configured: bool = False


class VectorServiceRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    api_key_configured: bool = True
    embedding_model: str
    rerank_model: str


class VoiceServiceRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key_configured: bool = True
    asr_url: str
    asr_model: str
    tts_url: str
    tts_model: str
    tts_voice: str


class MinerUServiceRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    api_key_configured: bool = True


class AccountServiceOverridesRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    search: SearchServiceRead | None = None
    vector: VectorServiceRead | None = None
    voice: VoiceServiceRead | None = None
    mineru: MinerUServiceRead | None = None


def serialize_configuration(
    slots: tuple[AccountModelSlotWrite, ...], services: AccountServiceOverridesWrite
) -> dict[str, Any]:
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
        "services": _serialize_services(services),
    }


def _serialize_services(services: AccountServiceOverridesWrite) -> dict[str, Any]:
    """Unwrap secrets only at the encrypted persistence boundary."""

    serialized: dict[str, Any] = {}
    if services.search is not None:
        search: dict[str, str] = {}
        if services.search.anysearch_url is not None:
            search["anysearch_url"] = str(services.search.anysearch_url)
            search["anysearch_api_key"] = services.search.anysearch_api_key.get_secret_value()  # type: ignore[union-attr]
        if services.search.tavily_url is not None:
            search["tavily_url"] = str(services.search.tavily_url)
            search["tavily_api_key"] = services.search.tavily_api_key.get_secret_value()  # type: ignore[union-attr]
        serialized["search"] = search
    if services.vector is not None:
        serialized["vector"] = {
            "url": str(services.vector.url),
            "api_key": services.vector.api_key.get_secret_value(),
            "embedding_model": services.vector.embedding_model,
            "rerank_model": services.vector.rerank_model,
        }
    if services.voice is not None:
        serialized["voice"] = {
            "api_key": services.voice.api_key.get_secret_value(),
            "asr_url": str(services.voice.asr_url),
            "asr_model": services.voice.asr_model,
            "tts_url": str(services.voice.tts_url),
            "tts_model": services.voice.tts_model,
            "tts_voice": services.voice.tts_voice,
        }
    if services.mineru is not None:
        serialized["mineru"] = {
            "url": str(services.mineru.url),
            "api_key": services.mineru.api_key.get_secret_value(),
        }
    return serialized


def parse_slots(configuration: dict[str, Any]) -> tuple[AccountModelSlotWrite, ...]:
    """Read the model slots from a current or legacy encrypted payload."""

    if configuration.get("schema_version") not in {
        MODEL_CONFIG_SCHEMA_VERSION,
        _LEGACY_MODEL_CONFIG_SCHEMA_VERSION,
    }:
        raise ValueError("account model configuration schema is not supported")
    raw_slots = configuration.get("slots")
    if not isinstance(raw_slots, list) or len(raw_slots) > 3:
        raise ValueError("account model configuration slots are invalid")
    slots = tuple(AccountModelSlotWrite.model_validate(item) for item in raw_slots)
    if len({slot.preference for slot in slots}) != len(slots):
        raise ValueError("account model configuration contains duplicate slots")
    return slots


def parse_services(configuration: dict[str, Any]) -> AccountServiceOverridesWrite:
    """Legacy model-only records deliberately retain deployment service defaults."""

    if configuration.get("schema_version") == _LEGACY_MODEL_CONFIG_SCHEMA_VERSION:
        return AccountServiceOverridesWrite()
    if configuration.get("schema_version") != MODEL_CONFIG_SCHEMA_VERSION:
        raise ValueError("account model configuration schema is not supported")
    raw_services = configuration.get("services", {})
    if not isinstance(raw_services, dict):
        raise ValueError("account service configuration is invalid")
    return AccountServiceOverridesWrite.model_validate(raw_services)


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


def read_services(configuration: dict[str, Any]) -> AccountServiceOverridesRead:
    services = parse_services(configuration)
    search = services.search
    return AccountServiceOverridesRead(
        search=(
            SearchServiceRead(
                anysearch_url=str(search.anysearch_url) if search.anysearch_url else None,
                anysearch_api_key_configured=search.anysearch_api_key is not None,
                tavily_url=str(search.tavily_url) if search.tavily_url else None,
                tavily_api_key_configured=search.tavily_api_key is not None,
            )
            if search is not None
            else None
        ),
        vector=(
            VectorServiceRead(
                url=str(services.vector.url),
                embedding_model=services.vector.embedding_model,
                rerank_model=services.vector.rerank_model,
            )
            if services.vector is not None
            else None
        ),
        voice=(
            VoiceServiceRead(
                asr_url=str(services.voice.asr_url),
                asr_model=services.voice.asr_model,
                tts_url=str(services.voice.tts_url),
                tts_model=services.voice.tts_model,
                tts_voice=services.voice.tts_voice,
            )
            if services.voice is not None
            else None
        ),
        mineru=(MinerUServiceRead(url=str(services.mineru.url)) if services.mineru else None),
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


def resolve_effective_settings(
    settings: Settings, configuration: dict[str, Any] | None
) -> Settings:
    """Overlay explicitly configured third-party services onto server defaults.

    This returns a request-owned Settings copy. It never mutates process settings,
    which keeps one account's provider keys isolated from another request.
    """

    if configuration is None:
        return settings
    services = parse_services(configuration)
    update: dict[str, Any] = {}
    if services.search is not None:
        if services.search.anysearch_url is not None:
            update["anysearch_url"] = services.search.anysearch_url
            update["anysearch_api_key"] = services.search.anysearch_api_key
        if services.search.tavily_url is not None:
            update["tavily_url"] = services.search.tavily_url
            update["tavily_api_key"] = services.search.tavily_api_key
    if services.vector is not None:
        update.update(
            siliconflow_url=services.vector.url,
            siliconflow_api_key=services.vector.api_key,
            embedding_model=services.vector.embedding_model,
            rerank_model=services.vector.rerank_model,
        )
    if services.voice is not None:
        update.update(
            mimo_api_key=services.voice.api_key,
            mimo_asr_url=services.voice.asr_url,
            asr_model=services.voice.asr_model,
            mimo_tts_url=services.voice.tts_url,
            tts_model=services.voice.tts_model,
            tts_voice=services.voice.tts_voice,
        )
    if services.mineru is not None:
        update.update(mineru_url=services.mineru.url, mineru_api_key=services.mineru.api_key)
    return settings.model_copy(update=update)


def has_service_override(configuration: dict[str, Any] | None, service: str) -> bool:
    if configuration is None:
        return False
    return getattr(parse_services(configuration), service) is not None

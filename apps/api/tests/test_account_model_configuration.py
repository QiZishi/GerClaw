"""Unit coverage for encrypted account-scoped model and service configuration."""

from __future__ import annotations

import pytest

from gerclaw_api.config import Settings
from gerclaw_api.services.account_model_configuration import (
    AccountModelSlotWrite,
    AccountServiceOverridesWrite,
    MinerUServiceWrite,
    SearchServiceWrite,
    VectorServiceWrite,
    VoiceServiceWrite,
    has_service_override,
    parse_services,
    parse_slots,
    read_services,
    read_slots,
    resolve_effective_configs,
    resolve_effective_settings,
    serialize_configuration,
)


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "database_url": "postgresql+asyncpg://user:secret@postgres/gerclaw_test",
            "redis_url": "redis://:secret@redis:6379/0",
            "qdrant_url": "http://qdrant:6333",
            "qdrant_api_key": "secret",
            "knowledge_base_path": "/tmp/knowledge-base",
            "auth_jwt_secret": "a-strong-test-jwt-secret-with-at-least-thirty-two-characters",
            "guest_identity_secret": "a-strong-test-guest-secret-with-at-least-thirty-two-chars",
            "data_encryption_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            "data_encryption_key_id": "test-v1",
            "agent_primary_url": "https://primary.example.com/v1",
            "agent_primary_api_key": "primary-secret",
            "agent_primary_model": "primary",
            "agent_backup1_url": "https://backup1.example.com/v1",
            "agent_backup1_api_key": "backup1-secret",
            "agent_backup1_model": "backup1",
            "agent_backup1_protocol": "dashscope",
            "agent_backup2_url": "https://backup2.example.com/v1",
            "agent_backup2_api_key": "backup2-secret",
            "agent_backup2_model": "backup2",
            "agent_backup2_protocol": "anthropic",
        }
    )


def _services() -> AccountServiceOverridesWrite:
    return AccountServiceOverridesWrite(
        search=SearchServiceWrite(
            anysearch_url="https://search.example.com",
            anysearch_api_key="search-secret",
            tavily_url="https://tavily.example.com",
            tavily_api_key="tavily-secret",
        ),
        vector=VectorServiceWrite(
            url="https://vector.example.com/v1",
            api_key="vector-secret",
            embedding_model="embedding-v1",
            rerank_model="rerank-v1",
        ),
        voice=VoiceServiceWrite(
            api_key="voice-secret",
            asr_url="https://voice.example.com/asr",
            asr_model="asr-v1",
            tts_url="https://voice.example.com/tts",
            tts_model="tts-v1",
            tts_voice="voice-a",
        ),
        mineru=MinerUServiceWrite(url="https://mineru.example.com", api_key="mineru-secret"),
    )


def test_serialized_configuration_round_trips_without_reading_any_secret() -> None:
    slots = (
        AccountModelSlotWrite(
            preference="primary",
            url="https://account-primary.example.com/v1",
            api_key="account-primary-secret",
            model_name="account-primary",
            protocol="openai",
            supports_image_input=False,
        ),
    )
    configuration = serialize_configuration(slots, _services())

    assert parse_slots(configuration) == slots
    assert parse_services(configuration).voice is not None
    assert read_slots(configuration)[0].api_key_configured is True
    assert read_slots(configuration)[0].supports_image_input is False
    public_services = read_services(configuration).model_dump_json()
    assert "configured" in public_services
    for secret in (
        "account-primary-secret",
        "search-secret",
        "vector-secret",
        "voice-secret",
        "mineru-secret",
    ):
        assert secret not in public_services


def test_legacy_and_invalid_configuration_boundaries_are_explicit() -> None:
    legacy = {
        "schema_version": "account-model-override-v1",
        "slots": [
            {
                "preference": "primary",
                "url": "https://primary.example.com/v1",
                "api_key": "legacy-secret",
                "model_name": "legacy",
                "protocol": "openai",
            }
        ],
    }

    assert parse_services(legacy) == AccountServiceOverridesWrite()
    assert has_service_override(legacy, "voice") is False

    with pytest.raises(ValueError, match="duplicate slots"):
        parse_slots({**legacy, "slots": [legacy["slots"][0], legacy["slots"][0]]})
    with pytest.raises(ValueError, match="schema is not supported"):
        parse_services({"schema_version": "unknown", "slots": []})
    with pytest.raises(ValueError, match="API Key"):
        SearchServiceWrite(anysearch_url="https://search.example.com")


def test_account_overrides_are_request_scoped_and_leave_deployment_settings_unchanged() -> None:
    settings = _settings()
    configuration = serialize_configuration(
        (
            AccountModelSlotWrite(
                preference="primary",
                url="https://account-primary.example.com/v1",
                api_key="account-primary-secret",
                model_name="account-primary",
                protocol="openai",
            ),
        ),
        _services(),
    )

    effective_models = resolve_effective_configs(settings, configuration)
    effective_settings = resolve_effective_settings(settings, configuration)

    assert [model.preference for model in effective_models] == ["primary", "backup1", "backup2"]
    assert effective_models[0].model_name == "account-primary"
    assert effective_models[1].model_name == "backup1"
    assert settings.agent_model_configs[0].model_name == "primary"
    assert effective_settings.embedding_model == "embedding-v1"
    assert effective_settings.rerank_model == "rerank-v1"
    assert effective_settings.asr_model == "asr-v1"
    assert effective_settings.mineru_url is not None
    assert settings.embedding_model != "embedding-v1"
    assert has_service_override(configuration, "vector") is True

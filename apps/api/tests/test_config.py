"""Configuration validation tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from gerclaw_api.config import Settings


def _values() -> dict[str, object]:
    return {
        "app_env": "production",
        "database_url": "postgresql+asyncpg://user:strong-database-secret@postgres/gerclaw",
        "redis_url": "redis://:strong-redis-secret@redis:6379/0",
        "qdrant_url": "http://qdrant:6333",
        "qdrant_api_key": "strong-qdrant-secret",
        "knowledge_base_path": Path("/knowledge-base"),
        "cors_origins": ["https://gerclaw.example.com"],
        "auth_jwt_secret": "strong-jwt-secret-with-at-least-thirty-two-characters",
        "guest_identity_secret": "strong-guest-identity-secret-with-at-least-thirty-two-chars",
        "data_encryption_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "data_encryption_key_id": "production-v1",
        "agent_primary_url": "https://primary.example.com/v1",
        "agent_primary_api_key": "strong-primary-secret",
        "agent_primary_model": "primary-model",
        "agent_primary_protocol": "openai",
        "agent_backup1_url": "https://backup1.example.com/v1",
        "agent_backup1_api_key": "strong-backup-one-secret",
        "agent_backup1_model": "backup1-model",
        "agent_backup1_protocol": "dashscope",
        "agent_backup2_url": "https://backup2.example.com/v1",
        "agent_backup2_api_key": "strong-backup-two-secret",
        "agent_backup2_model": "backup2-model",
        "agent_backup2_protocol": "anthropic",
        "mimo_api_key": "strong-mimo-secret-value",
        "mimo_asr_url": "https://voice.example.com/v1",
        "mimo_tts_url": "https://voice.example.com/v1",
        "asr_model": "mimo-v2.5-asr",
        "tts_model": "mimo-v2.5-tts",
        "tts_voice": "冰糖",
        "siliconflow_api_key": "strong-siliconflow-secret",
        "siliconflow_url": "https://api.siliconflow.cn/v1",
        "embedding_model": "BAAI/bge-m3",
        "rerank_model": "BAAI/bge-reranker-v2-m3",
        "anysearch_url": "https://api.anysearch.com",
        "anysearch_api_key": "strong-anysearch-secret",
        "tavily_url": "https://api.tavily.com",
        "tavily_api_key": "strong-tavily-secret",
        "mineru_url": "https://mineru.example.com/v1/agent",
        "mineru_api_key": "strong-mineru-secret",
    }


def test_production_settings_accept_explicit_safe_endpoints() -> None:
    settings = Settings.model_validate(_values())

    assert settings.cors_origin_strings == ["https://gerclaw.example.com"]
    assert [item.preference for item in settings.agent_model_configs] == [
        "primary",
        "backup1",
        "backup2",
    ]
    assert {item.max_output_tokens for item in settings.agent_model_configs} == {1_024}
    assert {item.timeout_seconds for item in settings.agent_model_configs} == {60.0}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("agent_model_timeout_seconds", 60.01),
        ("agent_model_max_output_tokens", 1_025),
    ],
)
def test_model_deadline_and_output_budget_are_hard_upper_bounds(field: str, value: object) -> None:
    values = _values()
    values[field] = value

    with pytest.raises(ValidationError):
        Settings.model_validate(values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cors_origins", ["http://localhost:3000"]),
        ("database_url", "sqlite+aiosqlite:///tmp/gerclaw.db"),
        ("qdrant_api_key", None),
    ],
)
def test_production_settings_reject_unsafe_configuration(field: str, value: object) -> None:
    values = _values()
    values[field] = value

    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_production_rejects_legacy_browser_exposed_secrets() -> None:
    values = _values()
    for key in tuple(values):
        if key.startswith("agent_"):
            values.pop(key)
    values.update(
        {
            "NEXT_PUBLIC_PRIMARY_URL": "https://primary.example.com/v1",
            "NEXT_PUBLIC_PRIMARY_API_KEY": "legacy-primary-key",
            "NEXT_PUBLIC_PRIMARY_MODEL": "primary-model",
            "NEXT_PUBLIC_PRIMARY_PROTOCOL": "openai",
            "NEXT_PUBLIC_BACKUP1_URL": "https://backup1.example.com/v1",
            "NEXT_PUBLIC_BACKUP1_API_KEY": "legacy-backup1-key",
            "NEXT_PUBLIC_BACKUP1_MODEL": "backup1-model",
            "NEXT_PUBLIC_BACKUP1_PROTOCOL": "dashscope",
            "NEXT_PUBLIC_BACKUP2_URL": "https://backup2.example.com/v1",
            "NEXT_PUBLIC_BACKUP2_API_KEY": "legacy-backup2-key",
            "NEXT_PUBLIC_BACKUP2_MODEL": "backup2-model",
            "NEXT_PUBLIC_BACKUP2_PROTOCOL": "openai",
        }
    )

    with pytest.raises(ValidationError, match="NEXT_PUBLIC"):
        Settings.model_validate(values)


def test_legacy_mvp_names_only_map_in_nonproduction_migration() -> None:
    values = _values()
    values["app_env"] = "development"
    for key in tuple(values):
        if key.startswith("agent_"):
            values.pop(key)
    values.update(
        {
            "NEXT_PUBLIC_PRIMARY_URL": "https://primary.example.com/v1",
            "NEXT_PUBLIC_PRIMARY_API_KEY": "legacy-primary-key",
            "NEXT_PUBLIC_PRIMARY_MODEL": "primary-model",
            "NEXT_PUBLIC_PRIMARY_PROTOCOL": "openai",
            "NEXT_PUBLIC_BACKUP1_URL": "https://backup1.example.com/v1",
            "NEXT_PUBLIC_BACKUP1_API_KEY": "legacy-backup1-key",
            "NEXT_PUBLIC_BACKUP1_MODEL": "backup1-model",
            "NEXT_PUBLIC_BACKUP1_PROTOCOL": "dashscope",
            "NEXT_PUBLIC_BACKUP2_URL": "https://backup2.example.com/v1",
            "NEXT_PUBLIC_BACKUP2_API_KEY": "legacy-backup2-key",
            "NEXT_PUBLIC_BACKUP2_MODEL": "backup2-model",
            "NEXT_PUBLIC_BACKUP2_PROTOCOL": "openai",
        }
    )

    settings = Settings.model_validate(values)

    assert len(settings.agent_model_configs) == 3
    assert settings.agent_model_configs[0].api_key.get_secret_value() == "legacy-primary-key"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("agent_primary_api_key", ""),
        ("mimo_api_key", "replace-me"),
        ("agent_primary_url", "http://primary.example.com/v1"),
    ],
)
def test_production_rejects_blank_placeholder_and_insecure_external_config(
    field: str, value: object
) -> None:
    values = _values()
    values[field] = value

    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_partial_agent_model_configuration_is_rejected_on_access() -> None:
    values = _values()
    values["app_env"] = "test"
    values["agent_primary_api_key"] = None
    settings = Settings.model_validate(values)

    with pytest.raises(ValueError, match="partially configured"):
        _ = settings.agent_model_configs

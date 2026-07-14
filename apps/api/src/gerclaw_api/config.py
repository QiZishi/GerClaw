"""Environment-backed application configuration."""

from __future__ import annotations

import base64
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import (
    AliasChoices,
    AnyHttpUrl,
    BaseModel,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_MARKERS = ("change-me", "replace-me", "local-", "example")


def _project_env_file() -> str | Path:
    """Find the repository-root env file without depending on the current directory."""

    for parent in Path(__file__).resolve().parents:
        if (parent / "docker-compose.yml").is_file():
            return parent / ".env"
    return ".env"


def _load_or_create_local_secret(filename: str, *, data_key: bool = False) -> SecretStr:
    """Persist a random local-only secret with owner-only permissions."""

    secret_dir = Path(
        os.getenv("GERCLAW_LOCAL_SECRET_DIR", "~/.local/share/gerclaw/secrets")
    ).expanduser()
    secret_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    secret_path = secret_dir / filename
    if secret_path.exists():
        return SecretStr(secret_path.read_text(encoding="utf-8").strip())
    value = (
        base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        if data_key
        else secrets.token_urlsafe(48)
    )
    try:
        descriptor = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return SecretStr(secret_path.read_text(encoding="utf-8").strip())
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(value)
    return SecretStr(value)


class AgentModelConfig(BaseModel):
    """One complete AgentScope model endpoint in the failover chain."""

    url: AnyHttpUrl
    api_key: SecretStr
    model_name: str = Field(min_length=1, max_length=128)
    protocol: Literal["openai", "dashscope", "anthropic"]
    preference: Literal["primary", "backup1", "backup2"]
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)


class Settings(BaseSettings):
    """Validated GerClaw runtime settings.

    Connection URLs are intentionally required. The application must never silently
    connect to an unexpected local or production service.
    """

    model_config = SettingsConfigDict(
        env_file=_project_env_file(),
        env_prefix="GERCLAW_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "GerClaw API"
    api_prefix: str = "/api/v1"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    max_request_body_bytes: int = Field(default=262_144, ge=16_384, le=2_097_152)
    rate_limit_requests: int = Field(default=100, ge=1, le=10_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3_600)
    max_events_per_trace: int = Field(default=10_000, ge=100, le=100_000)

    auth_jwt_secret: SecretStr = Field(
        default_factory=lambda: _load_or_create_local_secret("jwt.key"), min_length=32
    )
    auth_jwt_issuer: str = Field(default="gerclaw", min_length=2, max_length=128)
    auth_jwt_audience: str = Field(default="gerclaw-api", min_length=2, max_length=128)
    data_encryption_key: SecretStr = Field(
        default_factory=lambda: _load_or_create_local_secret("data.key", data_key=True),
        min_length=44,
    )
    data_encryption_key_id: str = Field(
        default="local-v1", min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$"
    )

    database_url: str = Field(repr=False, min_length=1)
    database_pool_size: int = Field(default=20, ge=1, le=200)
    database_max_overflow: int = Field(default=20, ge=0, le=400)
    database_pool_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    redis_url: str = Field(repr=False, min_length=1)
    redis_max_connections: int = Field(default=100, ge=1, le=1000)

    qdrant_url: AnyHttpUrl
    qdrant_api_key: SecretStr | None = None
    knowledge_base_path: Path
    knowledge_base_host_path: Path | None = None
    rag_collection_name: str = Field(
        default="gerclaw_local_medical_v1",
        min_length=3,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_-]+$",
    )
    rag_embedding_dimensions: int = Field(default=1_024, ge=128, le=4_096)
    rag_embedding_batch_size: int = Field(default=64, ge=1, le=128)
    rag_embedding_concurrency: int = Field(default=1, ge=1, le=32)
    rag_embedding_tokens_per_minute: int = Field(default=450_000, ge=10_000, le=10_000_000)
    rag_chunk_min_tokens: int = Field(default=256, ge=64, le=512)
    rag_chunk_target_tokens: int = Field(default=384, ge=128, le=512)
    rag_chunk_max_tokens: int = Field(default=512, ge=256, le=1_024)
    rag_chunk_overlap_tokens: int = Field(default=64, ge=0, le=256)
    rag_max_document_bytes: int = Field(default=8 * 1024 * 1024, ge=64 * 1024, le=25 * 1024 * 1024)
    rag_upsert_batch_size: int = Field(default=64, ge=1, le=256)
    rag_retrieval_candidates: int = Field(default=30, ge=5, le=100)
    rag_rerank_candidates: int = Field(default=20, ge=5, le=100)
    rag_min_rerank_score: float = Field(default=0.05, ge=0, le=1)

    cors_origins: list[AnyHttpUrl] = Field(min_length=1)
    agentscope_required_version: str = Field(default="2.0.4", pattern=r"^\d+\.\d+\.\d+$")
    readiness_cache_seconds: float = Field(default=5.0, ge=0, le=60)

    agent_primary_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_PRIMARY_URL", "AGENT_PRIMARY_URL", "NEXT_PUBLIC_PRIMARY_URL"
        ),
    )
    agent_primary_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_PRIMARY_API_KEY",
            "AGENT_PRIMARY_API_KEY",
            "NEXT_PUBLIC_PRIMARY_API_KEY",
        ),
    )
    agent_primary_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_PRIMARY_MODEL", "AGENT_PRIMARY_MODEL", "NEXT_PUBLIC_PRIMARY_MODEL"
        ),
    )
    agent_primary_protocol: Literal["openai", "dashscope", "anthropic"] | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_PRIMARY_PROTOCOL",
            "AGENT_PRIMARY_PROTOCOL",
            "NEXT_PUBLIC_PRIMARY_PROTOCOL",
        ),
    )
    agent_primary_preference: Literal["primary"] = Field(
        default="primary",
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_PRIMARY_PREFERENCE", "AGENT_PRIMARY_PREFERENCE"
        ),
    )

    agent_backup1_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_BACKUP1_URL", "AGENT_BACKUP1_URL", "NEXT_PUBLIC_BACKUP1_URL"
        ),
    )
    agent_backup1_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_BACKUP1_API_KEY",
            "AGENT_BACKUP1_API_KEY",
            "NEXT_PUBLIC_BACKUP1_API_KEY",
        ),
    )
    agent_backup1_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_BACKUP1_MODEL", "AGENT_BACKUP1_MODEL", "NEXT_PUBLIC_BACKUP1_MODEL"
        ),
    )
    agent_backup1_protocol: Literal["openai", "dashscope", "anthropic"] | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_BACKUP1_PROTOCOL",
            "AGENT_BACKUP1_PROTOCOL",
            "NEXT_PUBLIC_BACKUP1_PROTOCOL",
        ),
    )
    agent_backup1_preference: Literal["backup1"] = Field(
        default="backup1",
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_BACKUP1_PREFERENCE", "AGENT_BACKUP1_PREFERENCE"
        ),
    )

    agent_backup2_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_BACKUP2_URL", "AGENT_BACKUP2_URL", "NEXT_PUBLIC_BACKUP2_URL"
        ),
    )
    agent_backup2_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_BACKUP2_API_KEY",
            "AGENT_BACKUP2_API_KEY",
            "NEXT_PUBLIC_BACKUP2_API_KEY",
        ),
    )
    agent_backup2_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_BACKUP2_MODEL", "AGENT_BACKUP2_MODEL", "NEXT_PUBLIC_BACKUP2_MODEL"
        ),
    )
    agent_backup2_protocol: Literal["openai", "dashscope", "anthropic"] | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_BACKUP2_PROTOCOL",
            "AGENT_BACKUP2_PROTOCOL",
            "NEXT_PUBLIC_BACKUP2_PROTOCOL",
        ),
    )
    agent_backup2_preference: Literal["backup2"] = Field(
        default="backup2",
        validation_alias=AliasChoices(
            "GERCLAW_AGENT_BACKUP2_PREFERENCE", "AGENT_BACKUP2_PREFERENCE"
        ),
    )

    external_request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    mimo_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_MIMO_API_KEY",
            "MIMO_API_KEY",
            "NEXT_PUBLIC_MIMO_API_KEY",
            "NEXT_PUBLIC_ASR_API_KEY",
            "NEXT_PUBLIC_TTS_API_KEY",
        ),
    )
    mimo_asr_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_MIMO_ASR_URL", "MIMO_ASR_URL", "NEXT_PUBLIC_ASR_URL"
        ),
    )
    mimo_tts_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_MIMO_TTS_URL", "MIMO_TTS_URL", "NEXT_PUBLIC_TTS_URL"
        ),
    )
    mimo_auth_header: Literal["authorization", "api-key"] = "authorization"
    asr_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GERCLAW_ASR_MODEL", "ASR_MODEL", "NEXT_PUBLIC_ASR_MODEL"),
    )
    tts_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GERCLAW_TTS_MODEL", "TTS_MODEL", "NEXT_PUBLIC_TTS_MODEL"),
    )
    tts_voice: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GERCLAW_TTS_VOICE", "TTS_VOICE", "NEXT_PUBLIC_TTS_VOICE"),
    )

    siliconflow_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GERCLAW_SILICONFLOW_API_KEY", "SILICONFLOW_API_KEY"),
    )
    siliconflow_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias=AliasChoices("GERCLAW_SILICONFLOW_URL", "SILICONFLOW_URL"),
    )
    embedding_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GERCLAW_EMBEDDING_MODEL", "EMBEDDING_MODEL"),
    )
    rerank_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GERCLAW_RERANK_MODEL", "RERANK_MODEL"),
    )

    anysearch_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias=AliasChoices("GERCLAW_ANYSEARCH_URL", "ANYSEARCH_URL"),
    )
    anysearch_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_ANYSEARCH_API_KEY", "ANYSEARCH_API_KEY", "NEXT_PUBLIC_ANYSEARCH_API_KEY"
        ),
    )
    tavily_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias=AliasChoices("GERCLAW_TAVILY_URL", "TAVILY_URL"),
    )
    tavily_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_TAVILY_API_KEY", "TAVILY_API_KEY", "NEXT_PUBLIC_TAVILY_API_KEY"
        ),
    )
    mineru_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias=AliasChoices("GERCLAW_MINERU_URL", "MINERU_URL", "NEXT_PUBLIC_MINERU_URL"),
    )
    mineru_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GERCLAW_MINERU_API_KEY", "MINERU_API_KEY", "NEXT_PUBLIC_MINERU_API_KEY"
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def reject_production_legacy_secrets(cls, value: object) -> object:
        """Never allow browser-prefixed secrets to supply a production process."""

        if not isinstance(value, dict):
            return value
        environment = value.get(
            "app_env", value.get("GERCLAW_APP_ENV", os.getenv("GERCLAW_APP_ENV"))
        )
        if environment != "production":
            return value
        legacy = [
            str(key)
            for key, item in value.items()
            if str(key).upper().startswith("NEXT_PUBLIC_")
            and str(key).upper().endswith(("API_KEY", "TOKEN", "SECRET"))
            and item not in (None, "")
        ]
        if legacy:
            raise ValueError("production cannot consume NEXT_PUBLIC secret variables")
        return value

    @field_validator(
        "qdrant_api_key",
        "agent_primary_api_key",
        "agent_backup1_api_key",
        "agent_backup2_api_key",
        "mimo_api_key",
        "siliconflow_api_key",
        "anysearch_api_key",
        "tavily_api_key",
        "mineru_api_key",
        mode="before",
    )
    @classmethod
    def normalize_optional_secret(cls, value: object) -> object:
        """Treat whitespace-only optional credentials as missing, never configured."""

        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_production_safety(self) -> Settings:
        """Reject unsafe production-only configuration combinations."""

        configured_kb_path = self.knowledge_base_path.expanduser()
        if configured_kb_path.is_dir():
            self.knowledge_base_path = configured_kb_path.resolve()
        elif self.knowledge_base_host_path is not None:
            host_path = self.knowledge_base_host_path.expanduser()
            if not host_path.is_absolute():
                env_file = Path(_project_env_file())
                host_path = env_file.parent / host_path
            self.knowledge_base_path = host_path.resolve()

        if self.rag_chunk_overlap_tokens >= self.rag_chunk_target_tokens:
            raise ValueError("RAG chunk overlap must be smaller than the target chunk size")
        if self.rag_chunk_min_tokens > self.rag_chunk_target_tokens:
            raise ValueError("RAG minimum chunk size cannot exceed the target chunk size")
        if self.rag_chunk_target_tokens > self.rag_chunk_max_tokens:
            raise ValueError("RAG target chunk size cannot exceed the hard maximum")
        if self.rag_rerank_candidates > self.rag_retrieval_candidates:
            raise ValueError("RAG rerank candidates cannot exceed retrieval candidates")

        if self.app_env == "production":
            if not {"auth_jwt_secret", "data_encryption_key"}.issubset(self.model_fields_set):
                raise ValueError("production requires explicit JWT and data-encryption secrets")
            origins = {str(origin).rstrip("/") for origin in self.cors_origins}
            if any(not origin.startswith("https://") for origin in origins):
                raise ValueError("production CORS origins must use HTTPS")
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("production database must use postgresql+asyncpg")
            if len(self.agent_model_configs) != 3:
                raise ValueError("production requires primary, backup1, and backup2 agent models")
            required_external = {
                "mimo_api_key": self.mimo_api_key,
                "mimo_asr_url": self.mimo_asr_url,
                "mimo_tts_url": self.mimo_tts_url,
                "asr_model": self.asr_model,
                "tts_model": self.tts_model,
                "tts_voice": self.tts_voice,
                "siliconflow_api_key": self.siliconflow_api_key,
                "siliconflow_url": self.siliconflow_url,
                "embedding_model": self.embedding_model,
                "rerank_model": self.rerank_model,
                "anysearch_url": self.anysearch_url,
                "tavily_url": self.tavily_url,
                "tavily_api_key": self.tavily_api_key,
                "mineru_url": self.mineru_url,
                "mineru_api_key": self.mineru_api_key,
            }
            missing = [name for name, value in required_external.items() if value is None]
            if missing:
                raise ValueError(
                    "production external service configuration is incomplete: " + ", ".join(missing)
                )
            external_urls = (
                self.agent_primary_url,
                self.agent_backup1_url,
                self.agent_backup2_url,
                self.mimo_asr_url,
                self.mimo_tts_url,
                self.siliconflow_url,
                self.anysearch_url,
                self.tavily_url,
                self.mineru_url,
            )
            if any(url is not None and url.scheme != "https" for url in external_urls):
                raise ValueError("production external services must use HTTPS")

            database = urlsplit(
                self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
            )
            if not database.password or self._is_weak_secret(database.password):
                raise ValueError("production database password is missing or a placeholder")
            database_query = parse_qs(database.query)
            if database.hostname not in {"postgres", "localhost"} and database_query.get("ssl") != [
                "require"
            ]:
                raise ValueError("external production PostgreSQL must require TLS")

            redis = urlsplit(self.redis_url)
            if not redis.password or self._is_weak_secret(redis.password):
                raise ValueError("production Redis must require a strong password")
            if redis.hostname != "redis" and redis.scheme != "rediss":
                raise ValueError("external production Redis must use TLS")

            if self.qdrant_api_key is None or self._is_weak_secret(
                self.qdrant_api_key.get_secret_value()
            ):
                raise ValueError("production Qdrant must require a strong API key")
            if self.qdrant_url.host != "qdrant" and self.qdrant_url.scheme != "https":
                raise ValueError("external production Qdrant must use HTTPS")

            secrets = (
                self.auth_jwt_secret,
                self.data_encryption_key,
                self.agent_primary_api_key,
                self.agent_backup1_api_key,
                self.agent_backup2_api_key,
                self.mimo_api_key,
                self.siliconflow_api_key,
                self.tavily_api_key,
                self.mineru_api_key,
            )
            if any(
                secret is None or self._is_weak_secret(secret.get_secret_value())
                for secret in secrets
            ):
                raise ValueError("production secrets must be non-empty and non-placeholder")

        try:
            encryption_key = base64.b64decode(
                self.data_encryption_key.get_secret_value(), validate=True
            )
        except ValueError as error:
            raise ValueError("data encryption key must be valid base64") from error
        if len(encryption_key) != 32:
            raise ValueError("data encryption key must decode to exactly 32 bytes")
        return self

    @staticmethod
    def _is_weak_secret(value: str) -> bool:
        normalized = value.strip().casefold()
        return len(normalized) < 16 or any(marker in normalized for marker in PLACEHOLDER_MARKERS)

    @property
    def cors_origin_strings(self) -> list[str]:
        """Return normalized origins accepted by FastAPI CORS middleware."""

        return [str(origin).rstrip("/") for origin in self.cors_origins]

    @property
    def agent_model_configs(self) -> tuple[AgentModelConfig, ...]:
        """Return only complete model slots, rejecting partial credentials."""

        slots = (
            (
                "primary",
                self.agent_primary_url,
                self.agent_primary_api_key,
                self.agent_primary_model,
                self.agent_primary_protocol,
                self.agent_primary_preference,
            ),
            (
                "backup1",
                self.agent_backup1_url,
                self.agent_backup1_api_key,
                self.agent_backup1_model,
                self.agent_backup1_protocol,
                self.agent_backup1_preference,
            ),
            (
                "backup2",
                self.agent_backup2_url,
                self.agent_backup2_api_key,
                self.agent_backup2_model,
                self.agent_backup2_protocol,
                self.agent_backup2_preference,
            ),
        )
        configured: list[AgentModelConfig] = []
        for name, url, api_key, model, protocol, preference in slots:
            values = (url, api_key, model, protocol)
            if not any(value is not None for value in values):
                continue
            if not all(value is not None for value in values):
                raise ValueError(f"agent model slot {name} is partially configured")
            configured.append(
                AgentModelConfig(
                    url=url,
                    api_key=api_key,
                    model_name=model,
                    protocol=protocol,
                    preference=preference,
                    timeout_seconds=self.external_request_timeout_seconds,
                )
            )
        return tuple(configured)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache process-wide settings."""

    return Settings()

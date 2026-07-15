"""Strict provider-independent contracts for online evidence search."""

from __future__ import annotations

from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

SearchDomain = Literal["general", "health", "academic"]
SearchProviderName = Literal["anysearch", "tavily"]
AuthorityLevel = Literal["S", "A", "B", "C"]


class ProviderSearchResult(BaseModel):
    """Validated result immediately after an external provider boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=512)
    snippet: str = Field(min_length=1, max_length=4_000)
    url: AnyHttpUrl
    published_date: str | None = Field(default=None, max_length=64)
    score: float | None = Field(default=None, ge=0, le=1)

    @field_validator("title", "snippet")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("search text cannot be blank")
        return normalized


class SearchResult(BaseModel):
    """Public, citation-ready web evidence result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^web_[a-f0-9]{16}$")
    title: str = Field(min_length=1, max_length=512)
    snippet: str = Field(min_length=1, max_length=4_000)
    url: AnyHttpUrl
    source: str = Field(min_length=1, max_length=253)
    published_date: str | None = Field(default=None, max_length=64)
    authority_level: AuthorityLevel
    provider: SearchProviderName
    score: float | None = Field(default=None, ge=0, le=1)

    @field_validator("url")
    @classmethod
    def require_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("public search results must use HTTPS")
        return value


class SearchAttempt(BaseModel):
    """PHI-free provider attempt metadata suitable for Trace and metrics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: SearchProviderName
    operation: Literal["search", "extract"]
    outcome: Literal[
        "success",
        "empty",
        "network_error",
        "timeout",
        "rate_limited",
        "unavailable",
        "rejected",
        "invalid_response",
    ]
    retry_index: int = Field(ge=0, le=1)
    duration_ms: int = Field(ge=0)
    result_count: int = Field(default=0, ge=0, le=10)


class SearchStatus(BaseModel):
    """Configuration-only readiness projection without live billable calls."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ready: bool
    primary: Literal["anysearch"] = "anysearch"
    fallback: Literal["tavily"] = "tavily"
    primary_configured: bool
    fallback_configured: bool

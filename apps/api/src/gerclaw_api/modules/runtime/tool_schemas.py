"""Pydantic input boundaries for currently registered AgentScope tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

STRICT = ConfigDict(extra="forbid")


class SearchKnowledgeInput(BaseModel):
    model_config = STRICT

    query: str = Field(min_length=1, max_length=4_000)
    knowledge_bases: list[str] | None = Field(default=None, max_length=5)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("knowledge query cannot be blank")
        return normalized


class SearchMemoryInput(BaseModel):
    model_config = STRICT

    keywords: list[str] = Field(min_length=1, max_length=5)
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item or len(item) > 200 for item in normalized):
            raise ValueError("memory keywords must contain 1-200 characters")
        return normalized


class WebSearchInput(BaseModel):
    model_config = STRICT

    query: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=5, ge=1, le=10)
    domain: Literal["general", "health", "academic"] = "health"

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("web query cannot be blank")
        return normalized

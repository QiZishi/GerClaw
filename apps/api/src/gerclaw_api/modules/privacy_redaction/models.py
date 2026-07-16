"""Strict public contracts for privacy filtering decisions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RedactionCategory(StrEnum):
    """A bounded category that never carries the matched source text."""

    CONTROL = "control"
    PERSON_NAME = "person_name"
    PHONE = "phone"
    EMAIL = "email"
    ID_CARD = "id_card"
    CREDENTIAL = "credential"


class EgressPurpose(StrEnum):
    """A fixed external-processing purpose; it is not user-controlled."""

    EXTERNAL_SEARCH_QUERY = "external_search_query"
    EXTERNAL_TTS = "external_tts"
    EXTERNAL_ASR_AUDIO = "external_asr_audio"


class RedactionFinding(BaseModel):
    """PHI-free count suitable for an internal egress audit record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: RedactionCategory
    count: int = Field(ge=1, le=100)


class RedactionResult(BaseModel):
    """Safe egress projection plus its versioned, non-content decision summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=4_000)
    purpose: EgressPurpose
    policy_version: str = Field(pattern=r"^[1-9][0-9]{0,3}\.[0-9]{1,4}\.[0-9]{1,4}$")
    findings: tuple[RedactionFinding, ...] = Field(default_factory=tuple, max_length=6)

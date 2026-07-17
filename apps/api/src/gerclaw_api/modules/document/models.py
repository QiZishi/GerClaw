"""Strict parsed-document API and runtime contracts."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

STRICT = ConfigDict(extra="forbid")
_FILENAME_CONTROL = re.compile(r"[\x00-\x1f\\/]")


class UploadedDocumentCreate(BaseModel):
    """One already-parsed document from the trusted same-origin BFF flow."""

    model_config = STRICT

    session_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=255)
    media_type: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/markdown",
        "text/plain",
    ]
    parse_source: Literal["mineru", "local_text"]
    markdown: str = Field(min_length=1, max_length=2_000_000)

    @field_validator("filename")
    @classmethod
    def normalize_filename(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or _FILENAME_CONTROL.search(normalized):
            raise ValueError("filename is invalid")
        return normalized

    @field_validator("markdown")
    @classmethod
    def normalize_markdown(cls, value: str) -> str:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized or "\x00" in normalized:
            raise ValueError("markdown is invalid")
        return normalized


class UploadedDocumentRead(BaseModel):
    """Owner-visible metadata; parsed content stays server-side."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    document_id: uuid.UUID
    session_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=96)
    parse_source: Literal["mineru", "local_text"]
    status: Literal["active", "revoked"]
    content_characters: int = Field(gt=0, le=2_000_000)
    created_at: datetime


class UploadedDocumentDeleted(BaseModel):
    """Idempotent owner-scoped revocation acknowledgement."""

    model_config = STRICT

    document_id: uuid.UUID
    deleted: Literal[True] = True


class UploadedDocumentContext(BaseModel):
    """Validated untrusted document material passed only to the local Harness."""

    model_config = STRICT

    document_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=2_000_000)


class DocumentParseEgressPrepared(BaseModel):
    """Opaque provider-egress handle; it carries no document metadata."""

    model_config = STRICT

    egress_id: uuid.UUID


class DocumentParseEgressFinish(BaseModel):
    """The BFF may report only the terminal provider outcome."""

    model_config = STRICT

    outcome: Literal["succeeded", "failed"]

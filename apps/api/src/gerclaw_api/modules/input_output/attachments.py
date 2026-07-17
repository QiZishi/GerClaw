"""Validated, traceable visual input contracts shared by chat workflows."""

from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_IMAGE_MEDIA_TYPES = Literal["image/jpeg", "image/png", "image/webp", "image/gif"]
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_BASE64_CHARACTERS = 7_000_000


class ImageInput(BaseModel):
    """One browser-provided visual input, validated before persistence or model egress."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    media_type: _IMAGE_MEDIA_TYPES
    base64: str = Field(min_length=4, max_length=_MAX_BASE64_CHARACTERS)

    @field_validator("base64")
    @classmethod
    def validate_base64_image(cls, value: str) -> str:
        if value != value.strip() or value.startswith("data:"):
            raise ValueError("image base64 must not include a data URL prefix")
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("image base64 is invalid") from error
        if not decoded or len(decoded) > _MAX_IMAGE_BYTES:
            raise ValueError("image exceeds the supported size limit")
        return value

    @property
    def sha256(self) -> str:
        return hashlib.sha256(base64.b64decode(self.base64, validate=True)).hexdigest()

    @property
    def evidence_id(self) -> str:
        # Content-addressed IDs prevent a browser from inventing provenance and
        # keep the same image stable across retry of one trace.
        return f"ev_img{self.sha256[:24]}"

    @property
    def size_bytes(self) -> int:
        return len(base64.b64decode(self.base64, validate=True))

    def trace_record(self) -> dict[str, str | int]:
        """Encrypted trace payload for replay/Bad Case analysis only."""

        return {
            "evidence_id": self.evidence_id,
            "media_type": self.media_type,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "base64": self.base64,
        }

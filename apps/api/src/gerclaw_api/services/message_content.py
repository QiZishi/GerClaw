"""Strict projection of encrypted persisted message content."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from gerclaw_api.database.models import Message
from gerclaw_api.modules.contracts import Citation


class StoredMessageContentError(RuntimeError):
    """Stored encrypted content failed its public projection contract."""


class _StoredTextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=50_000)


_CITATIONS = TypeAdapter(list[Citation])


def read_message_text(message: Message) -> str:
    try:
        blocks = [_StoredTextBlock.model_validate(item) for item in message.content]
    except (ValidationError, TypeError) as error:
        raise StoredMessageContentError("stored message content is invalid") from error
    text = "\n".join(block.text for block in blocks).strip()
    if not text:
        raise StoredMessageContentError("stored message text is empty")
    return text


def read_message_citations(message: Message) -> tuple[Citation, ...]:
    try:
        citations = _CITATIONS.validate_python(
            message.message_metadata.get("citations", [])
        )
    except ValidationError as error:
        raise StoredMessageContentError("stored message citations are invalid") from error
    return tuple(citations[:50])

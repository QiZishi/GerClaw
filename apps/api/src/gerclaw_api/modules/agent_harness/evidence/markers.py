"""Bind model citation markers to the exact admitted terminal citation list."""

from __future__ import annotations

import re

_MODEL_MARKER = re.compile(r"\[(?P<prefix>[EWC])(?P<index>\d+)\]", re.IGNORECASE)


class CitationMarkerValidationError(RuntimeError):
    """Raised when model text refers to evidence the server did not admit."""


def bind_citation_markers(
    text: str,
    *,
    local_citation_count: int,
    web_citation_count: int,
    web_citation_offset: int,
) -> str:
    """Replace valid model E/W markers with server-owned C markers."""

    if min(local_citation_count, web_citation_count, web_citation_offset) < 0:
        raise ValueError("citation counts and offsets cannot be negative")

    def replace(match: re.Match[str]) -> str:
        prefix = match.group("prefix").upper()
        index = int(match.group("index"))
        if prefix == "C":
            raise CitationMarkerValidationError("model emitted reserved citation marker")
        if prefix == "E":
            if not 1 <= index <= local_citation_count:
                raise CitationMarkerValidationError("local citation marker is out of range")
            public_index = index
        else:
            if not 1 <= index <= web_citation_count:
                raise CitationMarkerValidationError("web citation marker is out of range")
            public_index = web_citation_offset + index
        return f"[C{public_index}]"

    return _MODEL_MARKER.sub(replace, text)

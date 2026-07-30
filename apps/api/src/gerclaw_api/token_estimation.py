"""Shared dependency-free token estimation for model context capacity."""

from __future__ import annotations

from collections.abc import Iterable


def estimate_text_tokens(values: Iterable[str]) -> int:
    """Conservatively approximate mixed Chinese/ASCII input from UTF-8 bytes."""

    return sum(max(1, (len(value.encode("utf-8")) + 2) // 3) for value in values if value)

"""Canonical safe SSE encoding shared by live and replay transports."""

from __future__ import annotations

import json
from collections.abc import Mapping


def encode_sse(
    event: str,
    data: Mapping[str, object],
    *,
    sequence: int | None = None,
) -> str:
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    event_id = f"id: {sequence}\n" if sequence is not None else ""
    return f"{event_id}event: {event}\ndata: {payload}\n\n"

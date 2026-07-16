"""Route-level bounded SSE queue control tests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from gerclaw_api.api.routes.chat import _TERMINAL, QueueItem, _force_enqueue, chat
from gerclaw_api.auth import AuthContext
from gerclaw_api.domain.chat_schemas import ChatCancelledData, ChatRequest
from gerclaw_api.modules.agent_harness import StreamEvent


def test_companion_contract_rejects_skills_and_uploaded_documents() -> None:
    with pytest.raises(ValidationError, match="does not accept Skills or uploaded files"):
        ChatRequest(
            session_id=uuid.uuid4(),
            message="我有些孤单。",
            loaded_skills=["health-education"],
            workflow="companion",
        )


@pytest.mark.asyncio
async def test_chat_rejects_loaded_skills_without_execute_scope_before_side_effects() -> None:
    payload = ChatRequest(
        session_id=uuid.uuid4(),
        message="请基于技能给出健康教育建议。",
        loaded_skills=["health-education"],
    )
    identity = AuthContext(
        actor_id="guest_reviewer01",
        tenant_id="tenant_review001",
        scopes=frozenset({"chat:write"}),
    )

    with pytest.raises(HTTPException) as caught:
        await chat(payload, object(), identity)  # type: ignore[arg-type]

    assert caught.value.status_code == 403
    assert cast(dict[str, str], caught.value.detail) == {
        "code": "AUTH_SCOPE_REQUIRED",
        "message": "missing skill:execute scope",
    }


def test_full_sse_queue_preserves_terminal_tool_result_cancel_and_sentinel() -> None:
    queue: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=128)
    for index in range(128):
        queue.put_nowait(
            StreamEvent(
                event_type="reasoning_summary",
                data={"content": f"bounded-{index}"},
                timestamp=datetime.now(UTC),
            )
        )

    tool_result = StreamEvent(
        event_type="tool_result",
        data={
            "tool_call_id": "tool_call_queue_full_001",
            "tool_name": "Skill",
            "status": "cancelled",
            "duration_ms": 1,
        },
        timestamp=datetime.now(UTC),
    )
    cancelled = ChatCancelledData(trace_id="trace_queue_full_0001")
    _force_enqueue(queue, tool_result)
    _force_enqueue(queue, cancelled)
    _force_enqueue(queue, _TERMINAL)

    items = [queue.get_nowait() for _ in range(queue.qsize())]
    assert items[-3:] == [tool_result, cancelled, _TERMINAL]

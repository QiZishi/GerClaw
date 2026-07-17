"""Contract tests for the real Harness-to-browser SSE validation boundary."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from gerclaw_api.modules.agent_harness import StreamEvent
from gerclaw_api.modules.validation import (
    RAGEvidenceContractValidationError,
    StreamContractValidationError,
    validate_harness_stream_event,
    validate_local_rag_evidence_provenance,
    validate_public_chat_stream_event,
)


def _safety() -> dict[str, object]:
    return {
        "reviewed": True,
        "disclaimer_applied": True,
        "deterministic_diagnosis_blocked": False,
        "high_risk_escalation_checked": True,
        "notices": ["medical_disclaimer_applied"],
    }


def _rag_provenance() -> dict[str, object]:
    return {
        "document_id": "a" * 64,
        "chunk_id": "b" * 64,
        "title": "审核用本地指南",
        "chapter": "风险评估",
        "category": "老年用药",
        "source_type": "guideline",
        "publish_year": 2024,
        "chunk_index": 2,
        "total_chunks": 8,
        "hybrid_score": 0.8,
        "rerank_score": 0.9,
    }


def test_harness_terminal_contract_requires_only_harness_owned_fields() -> None:
    event = StreamEvent(
        event_type="done",
        data={"full_text": "请携带检查资料就医。", "references": [], "safety": _safety()},
        timestamp=datetime.now(UTC),
    )

    validated = validate_harness_stream_event(event)

    assert validated.data["full_text"] == "请携带检查资料就医。"
    assert "trace_id" not in validated.data


def test_public_terminal_contract_requires_trace_and_session_provenance() -> None:
    event = StreamEvent(
        event_type="done",
        data={
            "full_text": "请携带检查资料就医。",
            "references": [],
            "safety": _safety(),
            "trace_id": "trace_validation_0001",
            "session_id": str(uuid.uuid4()),
            "replayed": False,
        },
        timestamp=datetime.now(UTC),
    )

    validated = validate_public_chat_stream_event(event)

    assert validated.data["trace_id"] == "trace_validation_0001"
    assert validated.data["replayed"] is False


def test_public_boundary_rejects_harness_only_done_and_unknown_event_fields() -> None:
    harness_done = StreamEvent(
        event_type="done",
        data={"full_text": "请携带检查资料就医。", "references": [], "safety": _safety()},
        timestamp=datetime.now(UTC),
    )
    malformed_delta = StreamEvent(
        event_type="text_delta",
        data={"content": "您好", "provider_secret": "must-not-cross-boundary"},
        timestamp=datetime.now(UTC),
    )

    with pytest.raises(StreamContractValidationError, match="invalid public-chat-sse-v1 done"):
        validate_public_chat_stream_event(harness_done)
    with pytest.raises(
        StreamContractValidationError,
        match="invalid public-chat-sse-v1 text_delta",
    ):
        validate_harness_stream_event(malformed_delta)


def test_local_rag_evidence_contract_accepts_complete_provenance() -> None:
    provenance = validate_local_rag_evidence_provenance(_rag_provenance())

    assert provenance.document_id == "a" * 64
    assert provenance.chunk_index == 2


@pytest.mark.parametrize(
    "mutate",
    (
        {"source_type": "untrusted"},
        {"chunk_index": 8},
        {"extra_provider_field": "must-not-cross-boundary"},
    ),
)
def test_local_rag_evidence_contract_rejects_incomplete_or_unknown_provenance(
    mutate: dict[str, object],
) -> None:
    metadata = _rag_provenance() | mutate

    with pytest.raises(RAGEvidenceContractValidationError, match="local-rag-evidence-v1"):
        validate_local_rag_evidence_provenance(metadata)

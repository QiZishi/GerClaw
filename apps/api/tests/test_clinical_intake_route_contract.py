"""Trace ownership and safe read-boundary contracts for intake routes."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from gerclaw_api.api.routes.clinical_intakes import (
    _module_name,
    get_medication_reconciliation,
    get_prescription_input_readiness,
)
from gerclaw_api.domain.enums import TraceEventStatus, TraceEventType
from gerclaw_api.domain.trace_schemas import TraceEventCreate, TraceStartRequest
from gerclaw_api.modules.prescription.models import (
    ClinicalIntakeFieldRead,
    ClinicalIntakeRead,
    PrescriptionInputReadiness,
)


def test_clinical_intake_trace_uses_the_actual_domain_owner() -> None:
    assert _module_name("prescription") == "prescription"
    assert _module_name("medication_review") == "medication_review"


def test_prescription_draft_trace_metadata_obeys_the_audit_allowlist() -> None:
    """The live generation route must never turn a telemetry typo into HTTP 500."""

    start = TraceStartRequest(
        session_id=uuid.uuid4(),
        execution_type="prescription.generate",
        attributes={
            "feature": "five_prescription",
            "module": "prescription",
            "operation": "generate_draft",
            "version": "five-prescription-input-v1",
            "request_fingerprint": "a" * 52,
        },
    )
    event = TraceEventCreate(
        event_id="event_" + "a" * 32 + "_generate_draft",
        event_type=TraceEventType.CLINICAL_INTAKE,
        status=TraceEventStatus.SUCCEEDED,
        payload={
            "feature": "prescription",
            "operation": "generate_draft",
            "version": "five-prescription-report-v1",
            "document_count": 1,
            "event_count": 2,
            "outcome": "needs_clinician_review",
            "success": True,
        },
        duration_ms=1,
    )

    assert start.attributes["version"] == "five-prescription-input-v1"
    assert event.payload["event_count"] == 2


class _Request:
    app: object


@pytest.mark.asyncio
async def test_medication_reconciliation_is_unavailable_for_prescription_intake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Service:
        async def get(self, *_args: object, **_kwargs: object) -> ClinicalIntakeRead:
            return ClinicalIntakeRead(
                intake_id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                kind="prescription",
                definition_version="clinical-intake-v1",
                status="collecting",
                revision=1,
                title="x",
                description="x",
                fields=[
                    ClinicalIntakeFieldRead(
                        id="health_goal", label="x", required=True, max_length=1, placeholder="x"
                    )
                ],
                answers={},
                document_ids=[],
                missing_required_fields=[],
                governance_notice="x",
                updated_at="2026-01-01T00:00:00Z",
            )

    async def _no_rate_limit(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes._service", lambda *_args: _Service()
    )
    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes._enforce_rate_limit", _no_rate_limit
    )
    with pytest.raises(HTTPException) as error:
        await get_medication_reconciliation(
            uuid.uuid4(),
            _Request(),
            object(),  # type: ignore[arg-type]
            SimpleNamespace(tenant_id="tenant", actor_id="actor"),  # type: ignore[arg-type]
        )
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_prescription_input_readiness_projects_counts_without_private_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake_id = uuid.uuid4()

    class _Service:
        async def prescription_input_readiness(
            self, requested_id: uuid.UUID, **_kwargs: object
        ) -> PrescriptionInputReadiness:
            assert requested_id == intake_id
            return PrescriptionInputReadiness(
                intake_id=intake_id,
                definition_version="clinical-intake-v1",
                answer_field_count=2,
                uploaded_document_count=1,
                governance_notice="医生审核尚未启用。",
            )

    async def _no_rate_limit(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes._service", lambda *_args: _Service()
    )
    monkeypatch.setattr(
        "gerclaw_api.api.routes.clinical_intakes._enforce_rate_limit", _no_rate_limit
    )

    result = await get_prescription_input_readiness(
        intake_id,
        _Request(),
        object(),  # type: ignore[arg-type]
        SimpleNamespace(tenant_id="tenant", actor_id="actor"),  # type: ignore[arg-type]
    )

    payload = result.model_dump_json()
    assert result.uploaded_document_count == 1
    assert result.review_draft_enabled is True
    assert result.clinical_output_enabled is False
    assert "MinerU extracted report text" not in payload
    assert "health_goal" not in payload

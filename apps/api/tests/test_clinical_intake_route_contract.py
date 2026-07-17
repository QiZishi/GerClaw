"""Trace ownership and safe read-boundary contracts for intake routes."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from gerclaw_api.api.routes.clinical_intakes import _module_name, get_medication_reconciliation
from gerclaw_api.modules.prescription.models import ClinicalIntakeFieldRead, ClinicalIntakeRead


def test_clinical_intake_trace_uses_the_actual_domain_owner() -> None:
    assert _module_name("prescription") == "prescription"
    assert _module_name("medication_review") == "medication_review"


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

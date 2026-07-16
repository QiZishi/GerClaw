"""Trace ownership contracts for the independently governed intake routes."""

from gerclaw_api.api.routes.clinical_intakes import _module_name


def test_clinical_intake_trace_uses_the_actual_domain_owner() -> None:
    assert _module_name("prescription") == "prescription"
    assert _module_name("medication_review") == "medication_review"

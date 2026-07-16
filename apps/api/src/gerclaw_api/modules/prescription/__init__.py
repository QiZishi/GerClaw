"""Fail-closed prescription-intake contracts; this module never issues a prescription."""

from gerclaw_api.modules.prescription.intake import (
    CLINICAL_INTAKE_DEFINITIONS,
    ClinicalIntakeDefinition,
    ClinicalIntakeField,
)

__all__ = ["CLINICAL_INTAKE_DEFINITIONS", "ClinicalIntakeDefinition", "ClinicalIntakeField"]

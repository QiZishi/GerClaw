"""Permit an explicit chronic-care read grant for a named doctor.

Revision ID: c52c814f2047
Revises: b51c814f2046
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c52c814f2047"
down_revision: str | Sequence[str] | None = "b51c814f2046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "valid_patient_access_grant_resource_scope", "patient_access_grants", type_="check"
    )
    op.create_check_constraint(
        "valid_patient_access_grant_resource_scope",
        "patient_access_grants",
        "resource_scope IN ('health_profile_read','cga_report_read','prescription_draft_review',"
        "'medication_review_read','risk_alert_read','chronic_care_read')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "valid_patient_access_grant_resource_scope", "patient_access_grants", type_="check"
    )
    op.create_check_constraint(
        "valid_patient_access_grant_resource_scope",
        "patient_access_grants",
        "resource_scope IN ('health_profile_read','cga_report_read','prescription_draft_review',"
        "'medication_review_read','risk_alert_read')",
    )

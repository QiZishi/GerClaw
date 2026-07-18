"""Allow patients to share saved medication-review artifacts with a doctor.

Revision ID: a31c814f2044
Revises: a21c814f2043
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a31c814f2044"
down_revision: str | Sequence[str] | None = "a21c814f2043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "valid_patient_access_grant_resource_scope",
        "patient_access_grants",
        type_="check",
    )
    op.create_check_constraint(
        "valid_patient_access_grant_resource_scope",
        "patient_access_grants",
        "resource_scope IN ('health_profile_read','cga_report_read','prescription_draft_review','medication_review_read')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "valid_patient_access_grant_resource_scope",
        "patient_access_grants",
        type_="check",
    )
    op.create_check_constraint(
        "valid_patient_access_grant_resource_scope",
        "patient_access_grants",
        "resource_scope IN ('health_profile_read','cga_report_read','prescription_draft_review')",
    )

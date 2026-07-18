"""Add patient-authorized doctor read access to risk alerts."""

from alembic import op

revision = "a41c814f2045"
down_revision = "a31c814f2044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "valid_patient_access_grant_resource_scope", "patient_access_grants", type_="check"
    )
    op.create_check_constraint(
        "valid_patient_access_grant_resource_scope",
        "patient_access_grants",
        "resource_scope IN ('health_profile_read','cga_report_read','prescription_draft_review','medication_review_read','risk_alert_read')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "valid_patient_access_grant_resource_scope", "patient_access_grants", type_="check"
    )
    op.create_check_constraint(
        "valid_patient_access_grant_resource_scope",
        "patient_access_grants",
        "resource_scope IN ('health_profile_read','cga_report_read','prescription_draft_review','medication_review_read')",
    )

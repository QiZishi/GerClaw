"""Add consented clinician reviews for five-prescription drafts.

Revision ID: c36d914f3150
Revises: b26c814f2041
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c36d914f3150"
down_revision: str | Sequence[str] | None = "b26c814f2041"
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
        "resource_scope IN ('health_profile_read','cga_report_read','prescription_draft_review')",
    )
    op.create_table(
        "prescription_draft_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("prescription_draft_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_actor_id", sa.String(length=128), nullable=False),
        sa.Column("doctor_actor_id", sa.String(length=128), nullable=False),
        sa.Column("draft_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('approved','returned')",
            name="valid_prescription_draft_review_decision",
        ),
        sa.CheckConstraint(
            "revision > 0", name="positive_prescription_draft_review_revision"
        ),
        sa.ForeignKeyConstraint(
            ["prescription_draft_id"], ["prescription_drafts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "prescription_draft_id",
            "doctor_actor_id",
            "revision",
            name="uq_prescription_draft_reviews_draft_doctor_revision",
        ),
    )
    op.create_index(
        "ix_prescription_draft_reviews_tenant_id",
        "prescription_draft_reviews",
        ["tenant_id"],
    )
    op.create_index(
        "ix_prescription_draft_reviews_prescription_draft_id",
        "prescription_draft_reviews",
        ["prescription_draft_id"],
    )
    op.create_index(
        "ix_prescription_draft_reviews_patient_actor_id",
        "prescription_draft_reviews",
        ["patient_actor_id"],
    )
    op.create_index(
        "ix_prescription_draft_reviews_doctor_actor_id",
        "prescription_draft_reviews",
        ["doctor_actor_id"],
    )
    op.create_index(
        "ix_prescription_draft_reviews_patient_created",
        "prescription_draft_reviews",
        ["tenant_id", "patient_actor_id", "reviewed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prescription_draft_reviews_patient_created",
        table_name="prescription_draft_reviews",
    )
    op.drop_index(
        "ix_prescription_draft_reviews_doctor_actor_id",
        table_name="prescription_draft_reviews",
    )
    op.drop_index(
        "ix_prescription_draft_reviews_patient_actor_id",
        table_name="prescription_draft_reviews",
    )
    op.drop_index(
        "ix_prescription_draft_reviews_prescription_draft_id",
        table_name="prescription_draft_reviews",
    )
    op.drop_index(
        "ix_prescription_draft_reviews_tenant_id",
        table_name="prescription_draft_reviews",
    )
    op.drop_table("prescription_draft_reviews")
    op.drop_constraint(
        "valid_patient_access_grant_resource_scope",
        "patient_access_grants",
        type_="check",
    )
    op.create_check_constraint(
        "valid_patient_access_grant_resource_scope",
        "patient_access_grants",
        "resource_scope IN ('health_profile_read','cga_report_read')",
    )

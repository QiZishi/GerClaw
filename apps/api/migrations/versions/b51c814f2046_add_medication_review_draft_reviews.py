"""Persist append-only clinician reviews for medication-review artifacts.

Revision ID: b51c814f2046
Revises: a41c814f2045
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from gerclaw_api.encryption import EncryptedText

revision: str = "b51c814f2046"
down_revision: str | Sequence[str] | None = "a41c814f2045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "medication_review_draft_reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("medication_review_draft_id", sa.UUID(), nullable=False),
        sa.Column("patient_actor_id", sa.String(length=128), nullable=False),
        sa.Column("doctor_actor_id", sa.String(length=128), nullable=False),
        sa.Column("draft_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("review_note", EncryptedText(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('approved','returned')",
            name="valid_medication_review_draft_review_decision",
        ),
        sa.CheckConstraint("revision > 0", name="positive_medication_review_draft_review_revision"),
        sa.ForeignKeyConstraint(
            ["medication_review_draft_id"], ["medication_review_drafts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "medication_review_draft_id",
            "doctor_actor_id",
            "revision",
            name="uq_medication_review_draft_reviews_draft_doctor_revision",
        ),
    )
    op.create_index(
        "ix_medication_review_draft_reviews_tenant_id",
        "medication_review_draft_reviews",
        ["tenant_id"],
    )
    op.create_index(
        "ix_medication_review_draft_reviews_medication_review_draft_id",
        "medication_review_draft_reviews",
        ["medication_review_draft_id"],
    )
    op.create_index(
        "ix_medication_review_draft_reviews_patient_actor_id",
        "medication_review_draft_reviews",
        ["patient_actor_id"],
    )
    op.create_index(
        "ix_medication_review_draft_reviews_doctor_actor_id",
        "medication_review_draft_reviews",
        ["doctor_actor_id"],
    )
    op.create_index(
        "ix_medication_review_draft_reviews_patient_created",
        "medication_review_draft_reviews",
        ["tenant_id", "patient_actor_id", "reviewed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_medication_review_draft_reviews_patient_created",
        table_name="medication_review_draft_reviews",
    )
    op.drop_index(
        "ix_medication_review_draft_reviews_doctor_actor_id",
        table_name="medication_review_draft_reviews",
    )
    op.drop_index(
        "ix_medication_review_draft_reviews_patient_actor_id",
        table_name="medication_review_draft_reviews",
    )
    op.drop_index(
        "ix_medication_review_draft_reviews_medication_review_draft_id",
        table_name="medication_review_draft_reviews",
    )
    op.drop_index(
        "ix_medication_review_draft_reviews_tenant_id",
        table_name="medication_review_draft_reviews",
    )
    op.drop_table("medication_review_draft_reviews")

"""Persist encrypted deterministic medication-review revisions.

Revision ID: a21c814f2043
Revises: a11c814f2042
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from gerclaw_api.encryption import EncryptedJSON

revision: str = "a21c814f2043"
down_revision: str | Sequence[str] | None = "a11c814f2042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "medication_review_drafts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("clinical_intake_id", sa.UUID(), nullable=False),
        sa.Column("clinical_intake_revision", sa.Integer(), nullable=False),
        sa.Column("ruleset_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content", EncryptedJSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('needs_clinician_review')",
            name="valid_medication_review_draft_status",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinical_intake_id"], ["clinical_intakes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_medication_review_drafts_tenant_id",
        "medication_review_drafts",
        ["tenant_id"],
    )
    op.create_index(
        "ix_medication_review_drafts_actor_id",
        "medication_review_drafts",
        ["actor_id"],
    )
    op.create_index(
        "ix_medication_review_drafts_owner_intake_created",
        "medication_review_drafts",
        ["tenant_id", "actor_id", "clinical_intake_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_medication_review_drafts_owner_intake_created",
        table_name="medication_review_drafts",
    )
    op.drop_index("ix_medication_review_drafts_actor_id", table_name="medication_review_drafts")
    op.drop_index("ix_medication_review_drafts_tenant_id", table_name="medication_review_drafts")
    op.drop_table("medication_review_drafts")

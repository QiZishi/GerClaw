"""Persist encrypted five-prescription draft revisions.

Revision ID: b06c814f2039
Revises: a85f0a2c6d942
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from gerclaw_api.encryption import EncryptedJSON

revision: str = "b06c814f2039"
down_revision: str | Sequence[str] | None = "a85f0a2c6d942"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prescription_drafts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("clinical_intake_id", sa.UUID(), nullable=False),
        sa.Column("template_version", sa.String(length=64), nullable=False),
        sa.Column("workflow_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content", EncryptedJSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('needs_clinician_review')", name="valid_prescription_draft_status"
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinical_intake_id"], ["clinical_intakes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prescription_drafts_tenant_id", "prescription_drafts", ["tenant_id"])
    op.create_index("ix_prescription_drafts_actor_id", "prescription_drafts", ["actor_id"])
    op.create_index(
        "ix_prescription_drafts_owner_intake_created",
        "prescription_drafts",
        ["tenant_id", "actor_id", "clinical_intake_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_prescription_drafts_owner_intake_created", table_name="prescription_drafts")
    op.drop_index("ix_prescription_drafts_actor_id", table_name="prescription_drafts")
    op.drop_index("ix_prescription_drafts_tenant_id", table_name="prescription_drafts")
    op.drop_table("prescription_drafts")

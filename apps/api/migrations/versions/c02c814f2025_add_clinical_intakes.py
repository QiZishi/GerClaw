"""Add encrypted, fail-closed clinical intake records.

Revision ID: c02c814f2025
Revises: b02c814f2024
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from gerclaw_api.encryption import EncryptedJSON

revision: str = "c02c814f2025"
down_revision: str | Sequence[str] | None = "b02c814f2024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinical_intakes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("definition_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("answers", EncryptedJSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('prescription','medication_review')", name="valid_clinical_intake_kind"),
        sa.CheckConstraint(
            "status IN ('collecting','information_complete_pending_governance')",
            name="valid_clinical_intake_status",
        ),
        sa.CheckConstraint("revision > 0", name="positive_clinical_intake_revision"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "actor_id",
            "session_id",
            "kind",
            name="uq_clinical_intakes_principal_session_kind",
        ),
    )
    op.create_index("ix_clinical_intakes_tenant_id", "clinical_intakes", ["tenant_id"])
    op.create_index("ix_clinical_intakes_actor_id", "clinical_intakes", ["actor_id"])
    op.create_index(
        "ix_clinical_intakes_owner_session_updated",
        "clinical_intakes",
        ["tenant_id", "actor_id", "session_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_clinical_intakes_owner_session_updated", table_name="clinical_intakes")
    op.drop_index("ix_clinical_intakes_actor_id", table_name="clinical_intakes")
    op.drop_index("ix_clinical_intakes_tenant_id", table_name="clinical_intakes")
    op.drop_table("clinical_intakes")

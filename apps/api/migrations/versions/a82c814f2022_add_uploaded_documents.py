"""add encrypted session-scoped uploaded documents

Revision ID: a82c814f2022
Revises: a72c814f2021
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a82c814f2022"
down_revision: str | None = "a72c814f2021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploaded_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(length=96), nullable=False),
        sa.Column("parse_source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_characters", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('active','revoked')", name="valid_status"),
        sa.CheckConstraint("content_characters > 0", name="positive_content_characters"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_uploaded_documents_tenant_id", "uploaded_documents", ["tenant_id"])
    op.create_index("ix_uploaded_documents_actor_id", "uploaded_documents", ["actor_id"])
    op.create_index(
        "ix_uploaded_documents_owner_session_active",
        "uploaded_documents",
        ["tenant_id", "actor_id", "session_id", "status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_table("uploaded_documents")

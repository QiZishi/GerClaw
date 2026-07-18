"""add encrypted CGA assessments

Revision ID: a72c814f2021
Revises: a62c814f2021
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a72c814f2021"
down_revision: str | None = "a62c814f2021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cga_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("scale_id", sa.String(length=32), nullable=False),
        sa.Column("definition_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("current_position", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("answers", sa.Text(), nullable=False),
        sa.Column("report", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("status IN ('active','completed','abandoned')", name="valid_status"),
        sa.CheckConstraint(
            "current_position >= 1 AND current_position <= 9", name="valid_position"
        ),
        sa.CheckConstraint("revision > 0", name="positive_revision"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cga_assessments_tenant_id", "cga_assessments", ["tenant_id"])
    op.create_index("ix_cga_assessments_actor_id", "cga_assessments", ["actor_id"])
    op.create_index(
        "ix_cga_assessments_owner_updated",
        "cga_assessments",
        ["tenant_id", "actor_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_table("cga_assessments")

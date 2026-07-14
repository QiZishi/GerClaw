"""add encrypted memory fact revision history

Revision ID: e41b8c2a2017
Revises: d7f403a12017
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e41b8c2a2017"
down_revision: str | None = "d7f403a12017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_fact_revisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("fact_id", sa.UUID(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("revision > 0", name=op.f("ck_memory_fact_revisions_positive_revision")),
        sa.ForeignKeyConstraint(
            ["fact_id"],
            ["memory_facts.id"],
            name=op.f("fk_memory_fact_revisions_fact_id_memory_facts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_memory_fact_revisions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_fact_revisions")),
        sa.UniqueConstraint("fact_id", "revision", name="uq_memory_fact_revisions_fact_revision"),
    )
    op.create_index(
        op.f("ix_memory_fact_revisions_tenant_id"),
        "memory_fact_revisions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_fact_revisions_tenant_user_created",
        "memory_fact_revisions",
        ["tenant_id", "user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_memory_fact_revisions_tenant_user_created",
        table_name="memory_fact_revisions",
    )
    op.drop_index(
        op.f("ix_memory_fact_revisions_tenant_id"),
        table_name="memory_fact_revisions",
    )
    op.drop_table("memory_fact_revisions")

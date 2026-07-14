"""add evidenced memory facts

Revision ID: d7f403a12017
Revises: bf1a2d7c2016
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7f403a12017"
down_revision: str | None = "bf1a2d7c2016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_facts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("source_session_id", sa.UUID(), nullable=True),
        sa.Column("source_trace_id", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("memory_type", sa.String(length=16), nullable=False),
        sa.Column("fact_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("vector_revision", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('basic_info','allergy','condition','medication','vital_sign',"
            "'assessment','event','social','preference','goal')",
            name=op.f("ck_memory_facts_valid_category"),
        ),
        sa.CheckConstraint(
            "memory_type IN ('stable','evolving','event')",
            name=op.f("ck_memory_facts_valid_memory_type"),
        ),
        sa.CheckConstraint(
            "status IN ('confirmed','pending','inactive')",
            name=op.f("ck_memory_facts_valid_status"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_memory_facts_valid_confidence"),
        ),
        sa.CheckConstraint("revision > 0", name=op.f("ck_memory_facts_positive_revision")),
        sa.CheckConstraint(
            "vector_revision >= 0", name=op.f("ck_memory_facts_nonnegative_vector_revision")
        ),
        sa.ForeignKeyConstraint(
            ["source_session_id"],
            ["sessions.id"],
            name=op.f("fk_memory_facts_source_session_id_sessions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_memory_facts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_facts")),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "fact_key", name="uq_memory_facts_tenant_user_key"
        ),
    )
    op.create_index(op.f("ix_memory_facts_tenant_id"), "memory_facts", ["tenant_id"], unique=False)
    op.create_index(
        op.f("ix_memory_facts_source_trace_id"),
        "memory_facts",
        ["source_trace_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_facts_tenant_user_status",
        "memory_facts",
        ["tenant_id", "user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_memory_facts_vector_sync",
        "memory_facts",
        ["status", "revision", "vector_revision"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_memory_facts_vector_sync", table_name="memory_facts")
    op.drop_index("ix_memory_facts_tenant_user_status", table_name="memory_facts")
    op.drop_index(op.f("ix_memory_facts_source_trace_id"), table_name="memory_facts")
    op.drop_index(op.f("ix_memory_facts_tenant_id"), table_name="memory_facts")
    op.drop_table("memory_facts")

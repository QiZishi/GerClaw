"""Add private ReAct context boundary lineage.

Revision ID: d24c814f2061
Revises: d23c814f2060
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from gerclaw_api.encryption import EncryptedJSON

revision: str = "d24c814f2061"
down_revision: str | None = "d23c814f2060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_run_context_boundaries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("boundary_kind", sa.String(length=32), nullable=False),
        sa.Column("model_call_count", sa.Integer(), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("projection", EncryptedJSON(), nullable=False),
        sa.Column("projection_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "boundary_kind IN ('before-model','before-tool')",
            name=op.f(
                "ck_agent_run_context_boundaries_valid_context_boundary_kind"
            ),
        ),
        sa.CheckConstraint(
            "fencing_token > 0",
            name=op.f(
                "ck_agent_run_context_boundaries_positive_context_boundary_fence"
            ),
        ),
        sa.CheckConstraint(
            "sequence > 0",
            name=op.f(
                "ck_agent_run_context_boundaries_positive_context_boundary_sequence"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name=op.f(
                "fk_agent_run_context_boundaries_run_id_agent_runs"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_agent_run_context_boundaries"),
        ),
        sa.UniqueConstraint(
            "run_id",
            "sequence",
            name="uq_agent_run_context_boundary_sequence",
        ),
    )
    op.create_index(
        "ix_agent_run_context_boundaries_run_created",
        "agent_run_context_boundaries",
        ["run_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_run_context_boundaries_run_created",
        table_name="agent_run_context_boundaries",
    )
    op.drop_table("agent_run_context_boundaries")

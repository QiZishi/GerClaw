"""Add append-only PlanNode transition audit.

Revision ID: d13c814f2059
Revises: c13c814f2058
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d13c814f2059"
down_revision: str | None = "c13c814f2058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_run_plan_node_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("fallback_for_node_id", sa.String(length=64), nullable=True),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "((status = 'failed' AND error_code IS NOT NULL) OR "
            "(status != 'failed' AND error_code IS NULL))",
            name=op.f("ck_agent_run_plan_node_events_valid_plan_node_event_error"),
        ),
        sa.CheckConstraint(
            "attempt >= 0",
            name=op.f("ck_agent_run_plan_node_events_nonnegative_plan_node_attempt"),
        ),
        sa.CheckConstraint(
            "fencing_token > 0",
            name=op.f("ck_agent_run_plan_node_events_positive_plan_node_event_fence"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','skipped')",
            name=op.f("ck_agent_run_plan_node_events_valid_plan_node_event_status"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name=op.f("fk_agent_run_plan_node_events_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_agent_run_plan_node_events"),
        ),
        sa.UniqueConstraint(
            "run_id",
            "node_id",
            "attempt",
            "status",
            name="uq_agent_run_plan_node_transition",
        ),
    )
    op.create_index(
        "ix_agent_run_plan_node_events_run_created",
        "agent_run_plan_node_events",
        ["run_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_run_plan_node_events_run_created",
        table_name="agent_run_plan_node_events",
    )
    op.drop_table("agent_run_plan_node_events")

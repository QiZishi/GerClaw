"""Separate recoverable interruption time from terminal completion time.

Revision ID: d93c814f2053
Revises: c83c814f2052
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d93c814f2053"
down_revision: str | None = "c83c814f2052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("interrupted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE agent_runs SET interrupted_at = completed_at, completed_at = NULL "
        "WHERE status = 'interrupted'"
    )
    op.drop_constraint(
        op.f("ck_agent_runs_valid_agent_run_terminal_time"),
        "agent_runs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_agent_runs_valid_agent_run_terminal_time"),
        "agent_runs",
        "((status IN ('completed','completed_with_warnings','failed','cancelled') "
        "AND completed_at IS NOT NULL) OR "
        "(status IN ('running','waiting_for_user','interrupted') "
        "AND completed_at IS NULL))",
    )
    op.create_check_constraint(
        op.f("ck_agent_runs_valid_agent_run_interruption_time"),
        "agent_runs",
        "status != 'interrupted' OR interrupted_at IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_agent_runs_valid_agent_run_interruption_time"),
        "agent_runs",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_agent_runs_valid_agent_run_terminal_time"),
        "agent_runs",
        type_="check",
    )
    op.execute(
        "UPDATE agent_runs SET completed_at = interrupted_at "
        "WHERE status = 'interrupted'"
    )
    op.create_check_constraint(
        op.f("ck_agent_runs_valid_agent_run_terminal_time"),
        "agent_runs",
        "((status IN ('completed','completed_with_warnings','failed','cancelled','interrupted') "
        "AND completed_at IS NOT NULL) OR "
        "(status IN ('running','waiting_for_user') AND completed_at IS NULL))",
    )
    op.drop_column("agent_runs", "interrupted_at")

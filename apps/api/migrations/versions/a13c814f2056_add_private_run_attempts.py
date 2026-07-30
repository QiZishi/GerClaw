"""Add private Run attempts and the current-valid projection pointer.

Revision ID: a13c814f2056
Revises: f13c814f2055
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a13c814f2056"
down_revision: str | None = "f13c814f2055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_run_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.String(length=128), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=128), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "expected_current_attempt_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("validation_feedback", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempt > 0", name="ck_agent_run_attempts_positive_agent_run_attempt"),
        sa.CheckConstraint(
            "fencing_token > 0",
            name="ck_agent_run_attempts_positive_agent_run_attempt_fence",
        ),
        sa.CheckConstraint(
            "status IN ('staging','validated','rejected','invalidated')",
            name="ck_agent_run_attempts_valid_agent_run_attempt_status",
        ),
        sa.CheckConstraint(
            "((status = 'staging' AND completed_at IS NULL) OR "
            "(status != 'staging' AND completed_at IS NOT NULL))",
            name="ck_agent_run_attempts_valid_agent_run_attempt_completion",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_agent_run_attempts_run_id_agent_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_run_attempts"),
        sa.UniqueConstraint(
            "run_id",
            "public_operation_id",
            "attempt",
            name="uq_agent_run_attempt_number",
        ),
    )
    op.create_index(
        "ix_agent_run_attempts_operation",
        "agent_run_attempts",
        ["run_id", "public_operation_id", "attempt"],
        unique=False,
    )
    op.create_table(
        "agent_run_attempt_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=128), nullable=False),
        sa.Column("public_summary", sa.Text(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ordinal > 0",
            name="ck_agent_run_attempt_events_positive_agent_run_attempt_event_ordinal",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_agent_run_attempt_events_nonnegative_agent_run_attempt_event_duration",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["agent_run_attempts.id"],
            name="fk_agent_run_attempt_events_attempt_id_agent_run_attempts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_run_attempt_events"),
        sa.UniqueConstraint(
            "attempt_id",
            "ordinal",
            name="uq_agent_run_attempt_event_ordinal",
        ),
    )
    op.create_index(
        "ix_agent_run_attempt_events_attempt",
        "agent_run_attempt_events",
        ["attempt_id", "ordinal"],
        unique=False,
    )
    op.add_column(
        "agent_runs",
        sa.Column("current_valid_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_runs_current_valid_attempt",
        "agent_runs",
        "agent_run_attempts",
        ["current_valid_attempt_id"],
        ["id"],
        ondelete="SET NULL",
        use_alter=True,
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_agent_runs_current_valid_attempt",
        "agent_runs",
        type_="foreignkey",
    )
    op.drop_column("agent_runs", "current_valid_attempt_id")
    op.drop_index(
        "ix_agent_run_attempt_events_attempt",
        table_name="agent_run_attempt_events",
    )
    op.drop_table("agent_run_attempt_events")
    op.drop_index(
        "ix_agent_run_attempts_operation",
        table_name="agent_run_attempts",
    )
    op.drop_table("agent_run_attempts")

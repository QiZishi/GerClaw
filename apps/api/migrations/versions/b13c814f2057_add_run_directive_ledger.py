"""Add the fenced user directive ledger.

Revision ID: b13c814f2057
Revises: a13c814f2056
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b13c814f2057"
down_revision: str | None = "a13c814f2056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "last_directive_sequence",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_sessions_nonnegative_session_directive_sequence"),
        "sessions",
        "last_directive_sequence >= 0",
    )
    op.create_table(
        "run_directives",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("successor_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("claimed_by_fencing_token", sa.BigInteger(), nullable=True),
        sa.Column("claim_boundary_id", sa.String(length=128), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
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
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("sequence > 0", name="ck_run_directives_positive_run_directive_sequence"),
        sa.CheckConstraint("revision > 0", name="ck_run_directives_positive_run_directive_revision"),
        sa.CheckConstraint(
            "mode IN ('interrupt_and_steer','queue_for_next_boundary')",
            name="ck_run_directives_valid_run_directive_mode",
        ),
        sa.CheckConstraint(
            "status IN ('pending','pending_next_run','claimed','applied','cancelled')",
            name="ck_run_directives_valid_run_directive_status",
        ),
        sa.CheckConstraint(
            "claimed_by_fencing_token IS NULL OR claimed_by_fencing_token > 0",
            name="ck_run_directives_positive_run_directive_claim_fence",
        ),
        sa.CheckConstraint(
            "((status IN ('claimed','applied') "
            "AND claimed_at IS NOT NULL "
            "AND claimed_by_fencing_token IS NOT NULL "
            "AND claim_boundary_id IS NOT NULL) OR "
            "(status NOT IN ('claimed','applied')))",
            name="ck_run_directives_valid_run_directive_claim",
        ),
        sa.CheckConstraint(
            "status != 'applied' OR applied_at IS NOT NULL",
            name="ck_run_directives_valid_run_directive_applied_time",
        ),
        sa.CheckConstraint(
            "status != 'cancelled' OR cancelled_at IS NOT NULL",
            name="ck_run_directives_valid_run_directive_cancelled_time",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["sessions.id"],
            name="fk_run_directives_conversation_id_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_run_id"],
            ["agent_runs.id"],
            name="fk_run_directives_target_run_id_agent_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["successor_run_id"],
            ["agent_runs.id"],
            name="fk_run_directives_successor_run_id_agent_runs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_run_directives"),
        sa.UniqueConstraint(
            "tenant_id",
            "actor_id",
            "idempotency_key",
            name="uq_run_directives_owner_idempotency",
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_run_directives_conversation_sequence",
        ),
    )
    op.create_index(
        "ix_run_directives_tenant_id",
        "run_directives",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_run_directives_actor_id",
        "run_directives",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        "ix_run_directives_target_status_sequence",
        "run_directives",
        ["target_run_id", "status", "sequence"],
        unique=False,
    )
    op.create_index(
        "ix_run_directives_successor_status_sequence",
        "run_directives",
        ["successor_run_id", "status", "sequence"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_run_directives_successor_status_sequence",
        table_name="run_directives",
    )
    op.drop_index(
        "ix_run_directives_target_status_sequence",
        table_name="run_directives",
    )
    op.drop_index("ix_run_directives_actor_id", table_name="run_directives")
    op.drop_index("ix_run_directives_tenant_id", table_name="run_directives")
    op.drop_table("run_directives")
    op.drop_constraint(
        op.f("ck_sessions_nonnegative_session_directive_sequence"),
        "sessions",
        type_="check",
    )
    op.drop_column("sessions", "last_directive_sequence")

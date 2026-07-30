"""Add current metadata-only evolution signal records.

Revision ID: f13c814f2055
Revises: e13c814f2054
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f13c814f2055"
down_revision: str | None = "e13c814f2054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evolution_signal_records",
        sa.Column("run_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("route", sa.String(length=16), nullable=False),
        sa.Column("run_status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column(
            "capability_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "skill_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("feedback_value", sa.Integer(), nullable=False),
        sa.Column("feedback_revision", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
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
            "route IN ('quick','standard','deep','emergency')",
            name=op.f("ck_evolution_signal_records_valid_evolution_signal_route"),
        ),
        sa.CheckConstraint(
            "run_status IN "
            "('waiting_for_user','completed','completed_with_warnings',"
            "'failed','cancelled','interrupted')",
            name=op.f("ck_evolution_signal_records_valid_evolution_signal_status"),
        ),
        sa.CheckConstraint(
            "risk_level IN ('low','medium','high','critical')",
            name=op.f("ck_evolution_signal_records_valid_evolution_signal_risk"),
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND duration_ms >= 0",
            name=op.f("ck_evolution_signal_records_nonnegative_evolution_signal_metrics"),
        ),
        sa.CheckConstraint(
            "feedback_value IN (-1,0,1) AND feedback_revision >= 0",
            name=op.f("ck_evolution_signal_records_valid_evolution_signal_feedback"),
        ),
        sa.PrimaryKeyConstraint(
            "run_fingerprint",
            name=op.f("pk_evolution_signal_records"),
        ),
    )
    op.create_index(
        "ix_evolution_signal_occurred",
        "evolution_signal_records",
        ["occurred_at", "run_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evolution_signal_occurred",
        table_name="evolution_signal_records",
    )
    op.drop_table("evolution_signal_records")

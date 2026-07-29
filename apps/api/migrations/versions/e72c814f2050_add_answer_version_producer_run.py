"""Record the Run that produced each immutable answer version.

Revision ID: e72c814f2050
Revises: d72c814f2049
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e72c814f2050"
down_revision: str | None = "d72c814f2049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "answer_versions",
        sa.Column("producer_run_id", sa.UUID(), nullable=True),
    )
    op.execute("UPDATE answer_versions SET producer_run_id = run_id")
    op.alter_column("answer_versions", "producer_run_id", nullable=False)
    op.create_foreign_key(
        "fk_answer_versions_producer_run",
        "answer_versions",
        "agent_runs",
        ["producer_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_answer_versions_producer_run_id",
        "answer_versions",
        ["producer_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_answer_versions_producer_run_id", table_name="answer_versions")
    op.drop_constraint(
        "fk_answer_versions_producer_run",
        "answer_versions",
        type_="foreignkey",
    )
    op.drop_column("answer_versions", "producer_run_id")

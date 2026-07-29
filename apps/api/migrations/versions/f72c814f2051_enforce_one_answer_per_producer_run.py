"""Enforce one immutable answer per producer Run.

Revision ID: f72c814f2051
Revises: e72c814f2050
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f72c814f2051"
down_revision: str | None = "e72c814f2050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_answer_versions_producer_run",
        "answer_versions",
        ["producer_run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_answer_versions_producer_run",
        table_name="answer_versions",
    )

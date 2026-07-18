"""Add encrypted trace replay input artifacts.

Revision ID: 3b5c9d1e7a42
Revises: fb0c814f2038
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3b5c9d1e7a42"
down_revision: str | Sequence[str] | None = "fb0c814f2038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "execution_traces", sa.Column("private_input_artifacts", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("execution_traces", "private_input_artifacts")

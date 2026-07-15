"""Add encrypted, non-score-bearing CGA supplemental detail.

Revision ID: b02c814f2024
Revises: a92c814f2023
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from gerclaw_api.encryption import EncryptedJSON

revision: str = "b02c814f2024"
down_revision: str | Sequence[str] | None = "a92c814f2023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cga_assessments",
        sa.Column("notes", EncryptedJSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cga_assessments", "notes")

"""Add encrypted five-prescription image inputs.

Revision ID: 85f0a2c6d941
Revises: 3b5c9d1e7a42
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "85f0a2c6d941"
down_revision: str | Sequence[str] | None = "3b5c9d1e7a42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clinical_intakes", sa.Column("image_inputs", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clinical_intakes", "image_inputs")

"""Allow the MMSE education selection plus its thirty screening items.

Revision ID: b16c814f2040
Revises: b06c814f2039
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b16c814f2040"
down_revision: str | Sequence[str] | None = "b06c814f2039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("valid_position", "cga_assessments", type_="check")
    op.create_check_constraint(
        "valid_position", "cga_assessments", "current_position >= 1 AND current_position <= 31"
    )


def downgrade() -> None:
    op.drop_constraint("valid_position", "cga_assessments", type_="check")
    op.create_check_constraint(
        "valid_position", "cga_assessments", "current_position >= 1 AND current_position <= 30"
    )

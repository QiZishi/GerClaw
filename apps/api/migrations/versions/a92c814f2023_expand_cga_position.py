"""Permit server-defined CGA scales with up to thirty ordered items.

Revision ID: a92c814f2023
Revises: a82c814f2022
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a92c814f2023"
down_revision: str | Sequence[str] | None = "a82c814f2022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("valid_position", "cga_assessments", type_="check")
    op.create_check_constraint(
        "valid_position", "cga_assessments", "current_position >= 1 AND current_position <= 30"
    )


def downgrade() -> None:
    op.drop_constraint("valid_position", "cga_assessments", type_="check")
    op.create_check_constraint(
        "valid_position", "cga_assessments", "current_position >= 1 AND current_position <= 9"
    )

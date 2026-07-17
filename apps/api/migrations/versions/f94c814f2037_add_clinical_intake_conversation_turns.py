"""Persist the bounded five-prescription clarification count.

Revision ID: f94c814f2037
Revises: f04c814f2036
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f94c814f2037"
down_revision: str | Sequence[str] | None = "f04c814f2036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clinical_intakes",
        sa.Column("conversation_turns", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "valid_clinical_intake_conversation_turns",
        "clinical_intakes",
        "conversation_turns >= 0 AND conversation_turns <= 5",
    )
    op.alter_column("clinical_intakes", "conversation_turns", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "valid_clinical_intake_conversation_turns", "clinical_intakes", type_="check"
    )
    op.drop_column("clinical_intakes", "conversation_turns")

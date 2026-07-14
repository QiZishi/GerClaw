"""Add monotonic database fencing for chat session ownership.

Revision ID: 9c17e2a62016
Revises: 8a6d5b012016
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "9c17e2a62016"
down_revision: str | None = "8a6d5b012016"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    sa.Sequence("chat_session_fencing_seq").create(op.get_bind())
    op.add_column(
        "sessions",
        sa.Column(
            "active_fencing_token",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "active_fencing_token")
    sa.Sequence("chat_session_fencing_seq").drop(op.get_bind())

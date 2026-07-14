"""Bind each active chat fencing token to its Trace.

Revision ID: bf1a2d7c2016
Revises: 9c17e2a62016
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "bf1a2d7c2016"
down_revision: str | None = "9c17e2a62016"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("active_fencing_trace_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "active_fencing_trace_id")

"""Allow deterministic chat red-flag alert sources.

Revision ID: e52c814f2028
Revises: d42c814f2027
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e52c814f2028"
down_revision: str | Sequence[str] | None = "d42c814f2027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("valid_source", "risk_alerts", type_="check")
    op.create_check_constraint("valid_source", "risk_alerts", "source IN ('cga','chat')")


def downgrade() -> None:
    op.drop_constraint("valid_source", "risk_alerts", type_="check")
    op.create_check_constraint("valid_source", "risk_alerts", "source IN ('cga')")

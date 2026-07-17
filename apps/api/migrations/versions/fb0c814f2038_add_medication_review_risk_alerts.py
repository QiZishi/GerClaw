"""Allow deterministic severe medication-review alert sources.

Revision ID: fb0c814f2038
Revises: f94c814f2037
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "fb0c814f2038"
down_revision: str | Sequence[str] | None = "f94c814f2037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("valid_source", "risk_alerts", type_="check")
    op.create_check_constraint(
        "valid_source",
        "risk_alerts",
        "source IN ('cga','chat','medication_review')",
    )


def downgrade() -> None:
    op.drop_constraint("valid_source", "risk_alerts", type_="check")
    op.create_check_constraint("valid_source", "risk_alerts", "source IN ('cga','chat')")

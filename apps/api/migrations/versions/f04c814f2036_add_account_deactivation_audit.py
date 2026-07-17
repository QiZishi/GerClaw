"""Allow audited local-account deactivation events.

Revision ID: f04c814f2036
Revises: e04c814f2035
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f04c814f2036"
down_revision: str | Sequence[str] | None = "e04c814f2035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "valid_identity_security_event_type", "identity_security_events", type_="check"
    )
    op.create_check_constraint(
        "valid_identity_security_event_type",
        "identity_security_events",
        "event_type IN ('register','login','refresh','logout','password_change','deactivate')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "valid_identity_security_event_type", "identity_security_events", type_="check"
    )
    op.create_check_constraint(
        "valid_identity_security_event_type",
        "identity_security_events",
        "event_type IN ('register','login','refresh','logout','password_change')",
    )

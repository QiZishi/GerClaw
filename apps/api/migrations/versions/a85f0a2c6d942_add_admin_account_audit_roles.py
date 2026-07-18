"""Permit auditable administrator account management.

Revision ID: a85f0a2c6d942
Revises: 85f0a2c6d941
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a85f0a2c6d942"
down_revision: str | Sequence[str] | None = "85f0a2c6d941"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "valid_identity_security_event_type", "identity_security_events", type_="check"
    )
    op.create_check_constraint(
        "valid_identity_security_event_type",
        "identity_security_events",
        "event_type IN ('register','login','refresh','logout','password_change','deactivate','admin_update','bootstrap')",
    )
    op.drop_constraint(
        "valid_identity_security_event_role", "identity_security_events", type_="check"
    )
    op.create_check_constraint(
        "valid_identity_security_event_role",
        "identity_security_events",
        "role IS NULL OR role IN ('patient','doctor','admin')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "valid_identity_security_event_role", "identity_security_events", type_="check"
    )
    op.create_check_constraint(
        "valid_identity_security_event_role",
        "identity_security_events",
        "role IS NULL OR role IN ('patient','doctor')",
    )
    op.drop_constraint(
        "valid_identity_security_event_type", "identity_security_events", type_="check"
    )
    op.create_check_constraint(
        "valid_identity_security_event_type",
        "identity_security_events",
        "event_type IN ('register','login','refresh','logout','password_change','deactivate')",
    )

"""bind session Skill actor and user to one principal

Revision ID: e31c814f2019
Revises: d30c814f2018
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e31c814f2019"
down_revision: str | None = "d30c814f2018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_users_tenant_external_id",
        "users",
        ["tenant_id", "external_id", "id"],
    )
    op.drop_constraint("fk_session_skills_owner_actor", "session_skills", type_="foreignkey")
    op.create_foreign_key(
        "fk_session_skills_owner_principal",
        "session_skills",
        "users",
        ["tenant_id", "actor_id", "user_id"],
        ["tenant_id", "external_id", "id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_session_skills_owner_principal", "session_skills", type_="foreignkey")
    op.create_foreign_key(
        "fk_session_skills_owner_actor",
        "session_skills",
        "users",
        ["tenant_id", "actor_id"],
        ["tenant_id", "external_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("uq_users_tenant_external_id", "users", type_="unique")

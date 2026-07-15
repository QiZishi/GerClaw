"""harden Skill ownership, name uniqueness, and encrypted storage

Revision ID: d30c814f2018
Revises: c29c814f2018
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d30c814f2018"
down_revision: str | None = "c29c814f2018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_users_tenant_id", "users", ["tenant_id", "id"])
    op.create_unique_constraint(
        "uq_sessions_tenant_user_id",
        "sessions",
        ["tenant_id", "user_id", "id"],
    )

    op.add_column(
        "skill_definitions",
        sa.Column("name_fingerprint", sa.String(length=64), nullable=True),
    )
    # Existing names are AES-GCM envelopes, so this one-time value only gives
    # legacy rows a non-sensitive identity. All new writes use a normalized
    # plaintext SHA-256 blind index and selected duplicate names still fail closed.
    op.execute("UPDATE skill_definitions SET name_fingerprint = md5(name)")
    op.alter_column("skill_definitions", "name_fingerprint", nullable=False)
    op.create_unique_constraint(
        "uq_skill_definitions_owner_name",
        "skill_definitions",
        ["tenant_id", "actor_id", "name_fingerprint"],
    )
    op.create_unique_constraint(
        "uq_skill_definitions_owner_id",
        "skill_definitions",
        ["tenant_id", "actor_id", "id"],
    )
    # The schema is deterministically reconstructed from encrypted source_markdown;
    # retaining this user-controlled duplicate in JSONB leaked parameter descriptions.
    op.drop_column("skill_definitions", "parameter_schema")

    op.drop_constraint(
        op.f("fk_skill_definition_revisions_skill_definition_id_skill_definitions"),
        "skill_definition_revisions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_skill_revisions_owner_definition",
        "skill_definition_revisions",
        "skill_definitions",
        ["tenant_id", "actor_id", "skill_definition_id"],
        ["tenant_id", "actor_id", "id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "session_skills",
        sa.Column("user_id", sa.UUID(), nullable=True),
    )
    op.execute(
        "UPDATE session_skills AS ss SET user_id = s.user_id "
        "FROM sessions AS s "
        "WHERE ss.session_id = s.id AND ss.tenant_id = s.tenant_id"
    )
    op.alter_column("session_skills", "user_id", nullable=False)
    op.drop_constraint(
        op.f("fk_session_skills_session_id_sessions"),
        "session_skills",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_session_skills_owner_actor",
        "session_skills",
        "users",
        ["tenant_id", "actor_id"],
        ["tenant_id", "external_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_session_skills_owner_session",
        "session_skills",
        "sessions",
        ["tenant_id", "user_id", "session_id"],
        ["tenant_id", "user_id", "id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_session_skills_owner_session", "session_skills", type_="foreignkey")
    op.drop_constraint("fk_session_skills_owner_actor", "session_skills", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_session_skills_session_id_sessions"),
        "session_skills",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("session_skills", "user_id")

    op.drop_constraint(
        "fk_skill_revisions_owner_definition",
        "skill_definition_revisions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_skill_definition_revisions_skill_definition_id_skill_definitions"),
        "skill_definition_revisions",
        "skill_definitions",
        ["skill_definition_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "skill_definitions",
        sa.Column(
            "parameter_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("skill_definitions", "parameter_schema", server_default=None)
    op.drop_constraint("uq_skill_definitions_owner_id", "skill_definitions", type_="unique")
    op.drop_constraint("uq_skill_definitions_owner_name", "skill_definitions", type_="unique")
    op.drop_column("skill_definitions", "name_fingerprint")

    op.drop_constraint("uq_sessions_tenant_user_id", "sessions", type_="unique")
    op.drop_constraint("uq_users_tenant_id", "users", type_="unique")

"""Add encrypted uploaded-document references to clinical intake.

Revision ID: c12d814f2026
Revises: c02c814f2025
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from gerclaw_api.encryption import EncryptedJSON

revision: str = "c12d814f2026"
down_revision: str | Sequence[str] | None = "c02c814f2025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable preserves old records without attempting to write unencrypted
    # defaults during migration. Service reads treat NULL as an empty reference set.
    op.add_column("clinical_intakes", sa.Column("document_ids", EncryptedJSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("clinical_intakes", "document_ids")

"""Persist evidence-bound clinician amendments beside prescription reviews.

Revision ID: c62c814f2048
Revises: c52c814f2047
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from gerclaw_api.encryption import EncryptedJSON, EncryptedText

revision: str = "c62c814f2048"
down_revision: str | Sequence[str] | None = "c52c814f2047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prescription_draft_reviews",
        sa.Column("amended_markdown", EncryptedText(), nullable=True),
    )
    op.add_column(
        "prescription_draft_reviews",
        sa.Column("amendment_evidence_ids", EncryptedJSON(), nullable=True),
    )
    op.add_column(
        "prescription_draft_reviews",
        sa.Column("amended_content_sha256", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prescription_draft_reviews", "amended_content_sha256")
    op.drop_column("prescription_draft_reviews", "amendment_evidence_ids")
    op.drop_column("prescription_draft_reviews", "amended_markdown")

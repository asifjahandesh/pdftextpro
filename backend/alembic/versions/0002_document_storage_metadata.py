"""Add file_size and file_checksum to documents

Revision ID: 0002_document_storage_metadata
Revises: 0001_initial_schema
Create Date: 2026-11-25 12:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_document_storage_metadata"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("file_size", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column("file_checksum", sa.String(length=64), server_default="", nullable=False),
    )
    op.create_index(
        "ix_documents_file_checksum",
        "documents",
        ["file_checksum"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_file_checksum", table_name="documents")
    op.drop_column("documents", "file_checksum")
    op.drop_column("documents", "file_size")

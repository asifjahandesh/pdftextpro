"""Initial schema for documents, document_pages, and processing_jobs

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-25 11:12:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("total_pages", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("language", sa.String(length=32), server_default="auto", nullable=False),
        sa.Column("extracted_text", sa.Text(), server_default="", nullable=False),
        sa.Column("completed_pages", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)

    op.create_table(
        "document_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), server_default="", nullable=False),
        sa.Column("method", sa.String(length=32), server_default="text", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="done", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "page_number", name="uq_document_pages_doc_page"),
    )
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"], unique=False)
    op.create_index("ix_document_pages_status", "document_pages", ["status"], unique=False)
    op.create_index(
        "ix_document_pages_doc_status",
        "document_pages",
        ["document_id", "status"],
        unique=False,
    )

    op.create_table(
        "processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("checkpoint_page", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batch_size", sa.Integer(), server_default="20", nullable=False),
        sa.Column("error", sa.Text(), server_default="", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processing_jobs_document_id", "processing_jobs", ["document_id"], unique=False)
    op.create_index(
        "ix_processing_jobs_celery_task_id",
        "processing_jobs",
        ["celery_task_id"],
        unique=False,
    )
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"], unique=False)
    op.create_index(
        "ix_processing_jobs_doc_status",
        "processing_jobs",
        ["document_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_doc_status", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_status", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_celery_task_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_document_id", table_name="processing_jobs")
    op.drop_table("processing_jobs")

    op.drop_index("ix_document_pages_doc_status", table_name="document_pages")
    op.drop_index("ix_document_pages_status", table_name="document_pages")
    op.drop_index("ix_document_pages_document_id", table_name="document_pages")
    op.drop_table("document_pages")

    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_table("documents")

import uuid
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    documents = relationship(
        "Document",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size = Column(BigInteger, nullable=False, default=0, server_default="0")
    file_checksum = Column(String(64), nullable=False, default="", server_default="", index=True)
    total_pages = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(32), nullable=False, default="queued", server_default="queued", index=True)
    language = Column(String(32), nullable=False, default="auto", server_default="auto")
    extracted_text = Column(Text, nullable=False, default="", server_default="")
    completed_pages = Column(Integer, nullable=False, default=0, server_default="0")
    error = Column(Text, nullable=False, default="", server_default="")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    owner = relationship("User", back_populates="documents")
    pages = relationship(
        "DocumentPage",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    jobs = relationship(
        "ProcessingJob",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_document_pages_doc_page"),
        Index("ix_document_pages_doc_status", "document_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number = Column(Integer, nullable=False)
    text = Column(Text, nullable=False, default="", server_default="")
    method = Column(String(32), nullable=False, default="text", server_default="text")
    status = Column(String(32), nullable=False, default="done", server_default="done", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    document = relationship("Document", back_populates="pages")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index("ix_processing_jobs_doc_status", "document_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    celery_task_id = Column(String(255), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="queued", server_default="queued", index=True)
    checkpoint_page = Column(Integer, nullable=False, default=0, server_default="0")
    batch_size = Column(Integer, nullable=False, default=20, server_default="20")
    error = Column(Text, nullable=False, default="", server_default="")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    document = relationship("Document", back_populates="jobs")

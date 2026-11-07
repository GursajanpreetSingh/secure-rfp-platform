import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import Classification, DocStatus
from app.models.types import db_enum

EMBEDDING_DIM = 1536


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint("level IN ('section', 'passage')", name="ck_chunk_level"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("chunks.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(String(10), default="passage")
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)

    content: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(255))
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )

    # Permission fields copied from the parent document. Never less restrictive.
    classification: Mapped[Classification] = mapped_column(db_enum(Classification), index=True)
    department: Mapped[str | None] = mapped_column(String(50))
    allowed_roles: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)
    allowed_purposes: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)
    status: Mapped[DocStatus] = mapped_column(db_enum(DocStatus), index=True)
    valid_until: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

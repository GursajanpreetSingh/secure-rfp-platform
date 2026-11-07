import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import Classification, DocStatus
from app.models.types import db_enum


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("logical_id", "version", name="uq_document_logical_version"),
        CheckConstraint("version >= 1", name="ck_document_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    logical_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, default=uuid.uuid4)
    version: Mapped[int] = mapped_column(Integer, default=1)

    filename: Mapped[str] = mapped_column(String(255))
    doc_type: Mapped[str] = mapped_column(String(50))
    department: Mapped[str | None] = mapped_column(String(50))
    classification: Mapped[Classification] = mapped_column(
        db_enum(Classification), default=Classification.INTERNAL, index=True
    )
    allowed_roles: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)
    allowed_purposes: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)
    status: Mapped[DocStatus] = mapped_column(
        db_enum(DocStatus), default=DocStatus.DRAFT, index=True
    )
    valid_until: Mapped[date | None] = mapped_column(Date)

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    storage_uri: Mapped[str] = mapped_column(String(500))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

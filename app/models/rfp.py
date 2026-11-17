import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

RUN_STATES = ("running", "completed", "failed")
AI_STATUSES = ("compliant", "partial", "non_compliant", "insufficient_evidence", "not_judged")
FINAL_STATUSES = ("compliant", "partial", "non_compliant", "insufficient_evidence")
REVIEW_STATES = ("pending", "approved", "edited", "rejected")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class RfpRun(Base):
    """One pass of the system over one RFP, started by one person.

    Only that person can read it. The answers inside were built from documents they were allowed
    to use at that moment.
    """

    __tablename__ = "rfp_runs"
    __table_args__ = (CheckConstraint(_in("state", RUN_STATES), name="ck_rfp_run_state"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    rfp_name: Mapped[str] = mapped_column(String(80))
    source_filename: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str] = mapped_column(String(20), default="rfp")
    state: Mapped[str] = mapped_column(String(20), default="running")
    requirement_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)


class RfpResult(Base):
    """The system's answer to one requirement, and what the human reviewer did with it."""

    __tablename__ = "rfp_results"
    __table_args__ = (
        UniqueConstraint("run_id", "requirement_id", name="uq_rfp_result_requirement"),
        CheckConstraint(_in("ai_status", AI_STATUSES), name="ck_rfp_result_ai_status"),
        CheckConstraint(_in("review_state", REVIEW_STATES), name="ck_rfp_result_review_state"),
        CheckConstraint(
            "final_status IS NULL OR " + _in("final_status", FINAL_STATUSES),
            name="ck_rfp_result_final_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rfp_runs.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)

    # The requirement, as read from the RFP.
    requirement_id: Mapped[str] = mapped_column(String(32))
    section: Mapped[str | None] = mapped_column(String(255))
    priority: Mapped[str] = mapped_column(String(20))
    requirement_text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)

    # What the system decided. Never edited after the run; the reviewer's choice goes below.
    ai_status: Mapped[str] = mapped_column(String(30))
    ai_reason: Mapped[str | None] = mapped_column(String(40))
    ai_rationale: Mapped[str] = mapped_column(Text, default="")
    downgraded_from: Mapped[str | None] = mapped_column(String(30))
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str | None] = mapped_column(String(80))

    # What the human decided. Nothing is exportable until this is approved or edited.
    review_state: Mapped[str] = mapped_column(String(20), default="pending")
    final_status: Mapped[str | None] = mapped_column(String(30))
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

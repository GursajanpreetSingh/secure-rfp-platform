"""Save RFP runs and let a person review them.

Rules enforced here, on top of the database's own checks:
- A run belongs to the person who started it. Anyone else gets "not found", and the attempt is
  written to the audit log.
- The system's answer is never changed. A reviewer's decision is stored beside it.
- Nothing counts as reviewed until a person approves, edits or rejects it. An answer the system
  could not produce (not_judged) cannot be approved, only replaced by an explicit choice.
- Every review is written to the audit log with who, what and when. Notes are not copied into
  the log, only their length.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, record_event
from app.models import RfpResult, RfpRun, User
from app.models.enums import AuditDecision, Purpose
from app.models.rfp import FINAL_STATUSES, REVIEW_STATES

if TYPE_CHECKING:
    from app.rfp.assess import Assessment
    from app.rfp.judge import Citation

MIN_NOTE_CHARS = 10
MAX_NOTE_CHARS = 2000
MAX_WARNINGS = 50

REVIEW_ACTIONS = {"approve": "approved", "edit": "edited", "reject": "rejected"}


class RunNotFound(LookupError):
    """The run does not exist, or it belongs to someone else. The caller cannot tell which."""


class ReviewError(ValueError):
    """The review request is not allowed. The message is safe to show to the reviewer."""


def _now() -> datetime:
    return datetime.now(UTC)


# --- saving a run ---------------------------------------------------------------------------


def create_run(
    db: Session,
    user: User,
    rfp_name: str,
    source_filename: str,
    requirement_count: int,
    warnings: Sequence[str] = (),
    request_id: str | None = None,
) -> RfpRun:
    run = RfpRun(
        created_by=user.id,
        rfp_name=rfp_name[:80],
        source_filename=source_filename[:255],
        requirement_count=requirement_count,
        warnings=[str(w)[:300] for w in warnings][:MAX_WARNINGS],
    )
    db.add(run)
    db.flush()
    record_event(
        db,
        AuditAction.RFP_RUN_STARTED,
        AuditDecision.INFO,
        user=user,
        resource_type="rfp_run",
        resource_id=run.id,
        purpose=Purpose.RFP,
        detail={"rfp": run.rfp_name, "requirements": requirement_count},
        request_id=request_id,
    )
    return run


def citation_to_json(citation: Citation) -> dict:
    return {
        "ref": citation.ref,
        "document_id": str(citation.document_id),
        "chunk_id": str(citation.chunk_id),
        "title": citation.title,
        "section": citation.section,
        "page": citation.page,
        "quote": citation.quote,
    }


def save_assessment(db: Session, run: RfpRun, position: int, assessment: Assessment) -> RfpResult:
    requirement, judgement = assessment.requirement, assessment.judgement
    if judgement is None:
        ai = {"ai_status": "not_judged", "ai_reason": assessment.error, "citations": []}
    else:
        ai = {
            "ai_status": judgement.status.value,
            "ai_reason": judgement.reason.value,
            "ai_rationale": judgement.rationale,
            "downgraded_from": judgement.downgraded_from.value
            if judgement.downgraded_from
            else None,
            "citations": [citation_to_json(c) for c in judgement.citations],
        }
    row = RfpResult(
        run_id=run.id,
        position=position,
        requirement_id=requirement.id[:32],
        section=(requirement.section or None) and requirement.section[:255],
        priority=requirement.priority[:20],
        requirement_text=requirement.text,
        page=getattr(requirement, "page", None),
        evidence_count=assessment.evidence_count,
        model=assessment.model,
        **ai,
    )
    db.add(row)
    db.flush()
    return row


def finish_run(
    db: Session, user: User, run: RfpRun, state: str = "completed", request_id: str | None = None
) -> RfpRun:
    run.state = state
    run.finished_at = _now()
    db.flush()
    counts = Counter(
        db.scalars(select(RfpResult.ai_status).where(RfpResult.run_id == run.id)).all()
    )
    record_event(
        db,
        AuditAction.RFP_RUN_FINISHED,
        AuditDecision.INFO if state == "completed" else AuditDecision.ERROR,
        user=user,
        resource_type="rfp_run",
        resource_id=run.id,
        purpose=Purpose.RFP,
        detail={"state": state, "results": dict(counts)},
        request_id=request_id,
    )
    return run


# --- reading a run --------------------------------------------------------------------------


def get_run(db: Session, user: User, run_id: uuid.UUID, request_id: str | None = None) -> RfpRun:
    """Return the run if the user started it. Otherwise say "not found" and log the attempt."""
    run = db.get(RfpRun, run_id)
    if run is None or run.created_by != user.id:
        record_event(
            db,
            AuditAction.ACCESS_DECISION,
            AuditDecision.DENY,
            user=user,
            resource_type="rfp_run",
            resource_id=run_id,
            purpose=Purpose.RFP,
            detail={"reason": "not_owner_or_missing"},
            request_id=request_id,
        )
        raise RunNotFound("no such run")
    return run


def list_results(db: Session, user: User, run_id: uuid.UUID) -> list[RfpResult]:
    run = get_run(db, user, run_id)
    return list(
        db.scalars(
            select(RfpResult).where(RfpResult.run_id == run.id).order_by(RfpResult.position)
        ).all()
    )


def run_summary(db: Session, user: User, run_id: uuid.UUID) -> dict:
    results = list_results(db, user, run_id)
    by_review = Counter(r.review_state for r in results)
    return {
        "total": len(results),
        "ai_status": dict(Counter(r.ai_status for r in results)),
        "review_state": {state: by_review.get(state, 0) for state in REVIEW_STATES},
        "pending": by_review.get("pending", 0),
        "ready_to_export": len(results) > 0 and by_review.get("pending", 0) == 0,
    }


# --- review ---------------------------------------------------------------------------------


def review_result(
    db: Session,
    user: User,
    run_id: uuid.UUID,
    requirement_id: str,
    action: str,
    final_status: str | None = None,
    note: str | None = None,
    request_id: str | None = None,
) -> RfpResult:
    """approve: keep the system's answer. edit: choose another status. reject: drop the answer."""
    run = get_run(db, user, run_id, request_id)
    if run.state != "completed":
        raise ReviewError("The run has not finished, so it cannot be reviewed yet.")
    if action not in REVIEW_ACTIONS:
        raise ReviewError("The action must be approve, edit or reject.")
    result = db.scalar(
        select(RfpResult).where(
            RfpResult.run_id == run.id, RfpResult.requirement_id == requirement_id
        )
    )
    if result is None:
        raise ReviewError("That requirement is not part of this run.")

    note = (note or "").strip()
    if action == "approve":
        if result.ai_status == "not_judged":
            raise ReviewError(
                "The system could not answer this one. Edit it and choose a status yourself."
            )
        if final_status not in (None, result.ai_status):
            raise ReviewError("To use a different status, choose edit instead of approve.")
        decided = result.ai_status
    elif action == "edit":
        if final_status not in FINAL_STATUSES:
            raise ReviewError(f"Choose one status: {', '.join(FINAL_STATUSES)}.")
        if len(note) < MIN_NOTE_CHARS:
            raise ReviewError(f"Say why in a note of at least {MIN_NOTE_CHARS} characters.")
        decided = final_status
    else:
        if len(note) < MIN_NOTE_CHARS:
            raise ReviewError(f"Say why in a note of at least {MIN_NOTE_CHARS} characters.")
        decided = None

    previous = result.review_state
    result.review_state = REVIEW_ACTIONS[action]
    result.final_status = decided
    result.reviewer_note = note[:MAX_NOTE_CHARS] or None
    result.reviewed_by = user.id
    result.reviewed_at = _now()
    db.flush()
    record_event(
        db,
        AuditAction.RFP_REVIEW,
        AuditDecision.INFO,
        user=user,
        resource_type="rfp_result",
        resource_id=result.id,
        purpose=Purpose.RFP,
        detail={
            "run_id": str(run.id),
            "requirement_id": requirement_id,
            "action": action,
            "ai_status": result.ai_status,
            "final_status": decided,
            "previous_state": previous,
            "note_length": len(note),
        },
        request_id=request_id,
    )
    return result

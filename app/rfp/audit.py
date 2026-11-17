"""Audit events for an RFP run. IDs, statuses and reason codes only, never document text."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.audit.service import AuditAction, record_event
from app.models import User
from app.models.enums import AuditDecision, Purpose

if TYPE_CHECKING:
    from app.rfp.assess import Assessment
    from app.rfp.guard import Suspicious


def audit_assessment(
    db: Session,
    user: User,
    rfp: str,
    assessment: Assessment,
    request_id: str | None = None,
    run_id: uuid.UUID | None = None,
):
    judgement = assessment.judgement
    detail: dict = {
        "rfp": rfp,
        "evidence_count": assessment.evidence_count,
        "documents_shown": [str(doc_id) for doc_id in assessment.document_ids],
        "model": assessment.model,
    }
    if run_id is not None:
        detail["run_id"] = str(run_id)
    if judgement is None:
        detail["error"] = assessment.error
        decision = AuditDecision.ERROR
    else:
        detail["status"] = judgement.status.value
        detail["reason"] = judgement.reason.value
        detail["downgraded_from"] = (
            judgement.downgraded_from.value if judgement.downgraded_from else None
        )
        detail["citations"] = [
            {"document_id": str(c.document_id), "chunk_id": str(c.chunk_id), "page": c.page}
            for c in judgement.citations
        ]
        decision = AuditDecision.INFO
    return record_event(
        db,
        AuditAction.RFP_REQUIREMENT_JUDGED,
        decision,
        user=user,
        resource_type="rfp_requirement",
        resource_id=assessment.requirement.id,
        purpose=Purpose.RFP,
        detail=detail,
        request_id=request_id,
    )


def audit_suspicious(
    db: Session,
    user: User,
    rfp: str,
    items: Sequence[Suspicious],
    request_id: str | None = None,
) -> list:
    """One event per piece of RFP text that tried to instruct the system. The text itself is not
    stored, only where it was and why it was flagged."""
    events = []
    for item in items:
        events.append(
            record_event(
                db,
                AuditAction.RFP_INJECTION_FLAGGED,
                AuditDecision.DENY,
                user=user,
                resource_type="rfp",
                resource_id=rfp[:64],
                purpose=Purpose.RFP,
                detail={
                    "section": (item.section or "")[:100],
                    "page": item.page,
                    "reasons": [str(reason) for reason in item.reasons],
                    "length": len(item.text),
                },
                request_id=request_id,
            )
        )
    return events

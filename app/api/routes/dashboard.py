from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.core.db import get_db
from app.models import AuditEvent, RfpResult, RfpRun, User
from app.models.enums import Role

router = APIRouter(tags=["dashboard"])


class OverviewOut(BaseModel):
    runs_total: int
    runs_running: int
    answers_total: int
    pending_review: int
    reviewed: int
    rejected: int
    status_counts: dict[str, int]
    compliance_rate: float | None


class ActivityOut(BaseModel):
    id: int
    occurred_at: datetime
    action: str
    decision: str
    resource_type: str | None
    resource_id: str | None
    # Only an auditor sees who did it and the details. Everyone else sees their own rows only.
    user_email: str | None = None
    detail: dict | None = None


@router.get("/rfp/overview", response_model=OverviewOut)
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Numbers for the dashboard, over this person's runs only.

    A reviewed answer counts with the status the reviewer chose. A pending one counts with the
    system's status. A rejected one is not counted.
    """
    state_rows = db.execute(
        select(RfpRun.state, func.count())
        .where(RfpRun.created_by == user.id)
        .group_by(RfpRun.state)
    ).all()
    states = {state: count for state, count in state_rows}

    rows = db.execute(
        select(RfpResult.ai_status, RfpResult.review_state, RfpResult.final_status, func.count())
        .join(RfpRun, RfpRun.id == RfpResult.run_id)
        .where(RfpRun.created_by == user.id)
        .group_by(RfpResult.ai_status, RfpResult.review_state, RfpResult.final_status)
    ).all()

    status_counts: dict[str, int] = {}
    pending = reviewed = rejected = total = 0
    for ai_status, review_state, final_status, count in rows:
        total += count
        if review_state == "rejected":
            rejected += count
            continue
        if review_state == "pending":
            pending += count
            counted = ai_status
        else:
            reviewed += count
            counted = final_status
        status_counts[counted] = status_counts.get(counted, 0) + count

    judged = sum(count for status, count in status_counts.items() if status != "not_judged")
    rate = round(100 * status_counts.get("compliant", 0) / judged, 1) if judged else None
    return OverviewOut(
        runs_total=sum(states.values()),
        runs_running=states.get("running", 0),
        answers_total=total,
        pending_review=pending,
        reviewed=reviewed,
        rejected=rejected,
        status_counts=status_counts,
        compliance_rate=rate,
    )


@router.get("/audit/recent", response_model=list[ActivityOut])
def recent_activity(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    is_auditor = user.role == Role.AUDITOR
    query = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if not is_auditor:
        query = query.where(AuditEvent.user_id == user.id)
    return [
        ActivityOut(
            id=row.id,
            occurred_at=row.occurred_at,
            action=row.action,
            decision=row.decision.value,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            user_email=row.user_email if is_auditor else None,
            detail=row.detail if is_auditor else None,
        )
        for row in db.scalars(query).all()
    ]

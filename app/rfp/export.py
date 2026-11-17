"""Export a reviewed run as a compliance matrix (CSV, opens in Excel).

Gates, all checked here and not in the screen that calls this:
- Only the person who started the run can export it.
- The run must be finished and every answer must have been approved, edited or rejected.
  One pending answer blocks the whole export.
- Rejected answers are left out. Approved and edited ones are included.
- Evidence is checked again against the access rules as they are NOW. A quote from a document
  the person can no longer use is replaced by a notice, not exported.
- No cell can start with a formula character, so opening the file cannot run anything.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, record_event
from app.auth.policy_types import Subject
from app.models import RfpResult, User
from app.models.enums import AuditDecision, Purpose
from app.retrieval.access_sql import ACCESS_SQL, access_params
from app.rfp.store import get_run, list_results

COLUMNS = [
    "Requirement ID",
    "Section",
    "Priority",
    "Requirement",
    "Compliance status",
    "Review",
    "Evidence",
]
STATUS_LABELS = {
    "compliant": "Compliant",
    "partial": "Partially compliant",
    "non_compliant": "Non-compliant",
    "insufficient_evidence": "Insufficient evidence",
}
REVIEW_LABELS = {"approved": "Approved as suggested", "edited": "Status set by reviewer"}
REDACTED = "[source no longer available to you]"

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")

_VISIBLE_SQL = text(
    f"SELECT ch.id FROM chunks ch WHERE ch.id = ANY(CAST(:ids AS uuid[])) AND {ACCESS_SQL}"
)


class ExportBlocked(ValueError):
    """The run cannot be exported yet. The message is safe to show to the person."""


def safe_cell(value: object) -> str:
    """Text for a spreadsheet cell that can never be read as a formula."""
    cell = "" if value is None else str(value)
    return "'" + cell if cell.startswith(_FORMULA_START) else cell


def subject_of(user: User) -> Subject:
    return Subject(
        id=user.id,
        role=user.role,
        department=user.department,
        clearance=user.clearance,
        is_active=user.is_active,
    )


def visible_chunk_ids(
    db: Session,
    user: User,
    chunk_ids: list[str],
    today: date | None = None,
    purpose: Purpose = Purpose.RFP,
) -> set[str]:
    """Which of these chunks the user may use right now, for this purpose."""
    if not chunk_ids:
        return set()
    params = access_params(subject_of(user), purpose, today or date.today())
    rows = db.execute(_VISIBLE_SQL, {**params, "ids": chunk_ids}).all()
    return {str(row[0]) for row in rows}


def _doc_code(title: str) -> str:
    return title.split("_", 1)[0]


def _evidence_cell(result: RfpResult, visible: set[str]) -> tuple[str, int]:
    lines: list[str] = []
    redacted = 0
    for citation in result.citations:
        if citation["chunk_id"] in visible:
            page = f" p{citation['page']}" if citation.get("page") is not None else ""
            lines.append(f'{_doc_code(citation["title"])}{page}: "{citation["quote"]}"')
        else:
            lines.append(REDACTED)
            redacted += 1
    return "\n".join(lines), redacted


def _file_name(rfp_name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", rfp_name).strip("._") or "rfp"
    return f"{stem}_compliance_matrix.csv"


def export_run_csv(
    db: Session, user: User, run_id: uuid.UUID, request_id: str | None = None
) -> tuple[str, bytes]:
    run = get_run(db, user, run_id, request_id)
    results = list_results(db, user, run_id)

    if run.state != "completed":
        raise ExportBlocked("The run has not finished.")
    if not results:
        raise ExportBlocked("The run has no answers.")
    pending = [r.requirement_id for r in results if r.review_state == "pending"]
    if pending:
        raise ExportBlocked(f"{len(pending)} answer(s) still need review: {', '.join(pending[:5])}")
    included = [r for r in results if r.review_state in REVIEW_LABELS]
    if not included:
        raise ExportBlocked("Every answer was rejected, so there is nothing to export.")

    cited = {c["chunk_id"] for r in included for c in r.citations}
    visible = visible_chunk_ids(db, user, sorted(cited))

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    redacted_total = 0
    for result in included:
        evidence, redacted = _evidence_cell(result, visible)
        redacted_total += redacted
        writer.writerow(
            [
                safe_cell(value)
                for value in (
                    result.requirement_id,
                    result.section,
                    result.priority,
                    result.requirement_text,
                    STATUS_LABELS[result.final_status],
                    REVIEW_LABELS[result.review_state],
                    evidence,
                )
            ]
        )

    record_event(
        db,
        AuditAction.RFP_EXPORTED,
        AuditDecision.INFO,
        user=user,
        resource_type="rfp_run",
        resource_id=run.id,
        purpose=Purpose.RFP,
        detail={
            "format": "csv",
            "rows": len(included),
            "left_out_rejected": len(results) - len(included),
            "evidence_redacted": redacted_total,
        },
        request_id=request_id,
    )
    return _file_name(run.rfp_name), buffer.getvalue().encode("utf-8-sig")

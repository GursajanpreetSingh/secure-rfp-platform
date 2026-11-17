"""Start a run and carry it out. Used by the API; the command-line script has its own copy.

Starting is quick (read the RFP, save an empty run) and happens while the person waits.
Carrying out is slow (one model call per requirement) and happens in the background. Each
answer is committed as soon as it exists, so a screen can show progress, and a crash leaves
the finished answers in place and the run marked as failed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.ingestion.extract import extract
from app.models import RfpRun, User
from app.models.enums import Purpose
from app.retrieval.search import search
from app.rfp.assess import MAX_EVIDENCE, Assessment, SearchFn, assess_rfp
from app.rfp.audit import audit_assessment, audit_suspicious
from app.rfp.export import subject_of
from app.rfp.parse import parse_rfp
from app.rfp.store import create_run, finish_run, save_assessment

if TYPE_CHECKING:
    from app.rfp.assess import ModelAsk
    from app.rfp.parse import ParsedRfp, Requirement


class NoRequirements(ValueError):
    """The file was read, but no requirements were found in it."""


@dataclass(frozen=True)
class StartedRun:
    run: RfpRun
    requirements: list[Requirement]
    parsed: ParsedRfp


def read_rfp(path: Path) -> ParsedRfp:
    """Read a file and find its requirements. Raises NoRequirements if there are none."""
    parsed = parse_rfp(extract(path))
    if not parsed.requirements:
        raise NoRequirements("No requirements were found in this file.")
    return parsed


def start_run(
    db: Session,
    user: User,
    parsed: ParsedRfp,
    rfp_name: str,
    source_name: str,
    request_id: str | None = None,
) -> StartedRun:
    """Save an empty run for an already-read RFP and audit anything suspicious in it."""
    if parsed.suspicious:
        audit_suspicious(db, user, rfp_name, parsed.suspicious, request_id)
    run = create_run(
        db, user, rfp_name, source_name, len(parsed.requirements), parsed.warnings, request_id
    )
    db.flush()
    return StartedRun(run=run, requirements=list(parsed.requirements), parsed=parsed)


def make_search_fn(db: Session, user: User, embedder, top_k: int = MAX_EVIDENCE) -> SearchFn:
    """A search bound to this user, so that the permission filter cannot be left out."""
    subject = subject_of(user)

    def search_fn(question: str):
        return search(db, subject, question, Purpose.RFP, embedder, top_k=top_k)

    return search_fn


def execute_run(
    db: Session,
    user: User,
    run: RfpRun,
    requirements: Sequence[Requirement],
    search_fn: SearchFn,
    ask: ModelAsk | Callable,
    request_id: str | None = None,
    limit: int = MAX_EVIDENCE,
) -> RfpRun:
    """Judge every requirement, saving each answer as it arrives, then close the run."""
    position = 0

    def on_result(assessment: Assessment) -> None:
        nonlocal position
        position += 1
        audit_assessment(db, user, run.rfp_name, assessment, request_id, run.id)
        save_assessment(db, run, position, assessment)
        db.commit()  # progress is visible to a screen that is polling

    try:
        assess_rfp(requirements, search_fn, ask, on_result=on_result, limit=limit)
    except Exception:
        db.rollback()
        finish_run(db, user, run, "failed", request_id)
        db.commit()
        raise
    finish_run(db, user, run, "completed", request_id)
    db.commit()
    return run

import logging
import re
import tempfile
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, record_event
from app.auth.deps import get_current_user
from app.core.config import get_settings
from app.core.db import SessionLocal, get_db
from app.models import RfpRun, User
from app.models.enums import AuditDecision, Purpose, Role
from app.rfp.export import ExportBlocked, export_run_csv
from app.rfp.pipeline import NoRequirements, execute_run, make_search_fn, read_rfp, start_run
from app.rfp.schemas import ResultOut, ReviewIn, RunDetail, RunOut
from app.rfp.store import (
    ReviewError,
    RunNotFound,
    get_run,
    list_results,
    review_result,
    run_summary,
)

router = APIRouter(prefix="/rfp", tags=["rfp"])
log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_SUFFIXES = {".pdf": b"%PDF", ".docx": b"PK", ".txt": None}
RUN_ROLES = {Role.EMPLOYEE, Role.EXECUTIVE}
STALE_AFTER = timedelta(hours=2)  # a run "running" longer than this no longer blocks a new one


# --- things tests can replace ---------------------------------------------------------------


def get_session_factory() -> Callable[[], Session]:
    return SessionLocal


@lru_cache
def _llm():
    from app.llm.client import build_llm

    settings = get_settings()
    return build_llm(
        settings.llm_provider,
        settings.llm_api_key.get_secret_value(),
        settings.llm_models,
        settings.llm_timeout_ms,
    )


@lru_cache
def _embedder():
    from app.retrieval.embedder import get_embedder

    return get_embedder()


def execute_in_background(
    factory: Callable[[], Session], user_id: uuid.UUID, run_id: uuid.UUID, requirements, request_id
) -> None:
    """Judge the requirements of a run with its own database session. Never raises."""
    from app.rfp.assess import ModelAsk

    try:
        with factory() as db:
            user, run = db.get(User, user_id), db.get(RfpRun, run_id)
            search_fn = make_search_fn(db, user, _embedder())
            execute_run(db, user, run, requirements, search_fn, ModelAsk(_llm()), request_id)
    except Exception:
        log.exception("run %s failed", run_id)


def get_executor() -> Callable:
    return execute_in_background


# --- helpers --------------------------------------------------------------------------------


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "no such run")


def _owned_run(db: Session, user: User, run_id: uuid.UUID) -> RfpRun:
    try:
        return get_run(db, user, run_id)
    except RunNotFound:
        db.commit()  # keep the audit row that records the refusal
        raise _not_found() from None


def _clean_name(raw: str | None) -> str:
    name = Path(raw or "").name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return (name or "rfp")[:200]


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file is too large")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file is too large")
    return bytes(data)


# --- routes ---------------------------------------------------------------------------------


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def create(
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: Callable = Depends(get_session_factory),
    executor: Callable = Depends(get_executor),
):
    """Send the RFP file as the request body, with its name in the X-Filename header."""
    request_id = uuid.uuid4().hex[:16]
    if user.role not in RUN_ROLES:
        record_event(
            db,
            AuditAction.ACCESS_DECISION,
            AuditDecision.DENY,
            user=user,
            resource_type="rfp_run",
            purpose=Purpose.RFP,
            detail={"reason": "role_not_allowed"},
            request_id=request_id,
        )
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "your account cannot run RFPs")

    filename = _clean_name(request.headers.get("x-filename"))
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "use a PDF, DOCX or TXT file")

    busy = db.scalar(
        select(func.count())
        .select_from(RfpRun)
        .where(
            RfpRun.created_by == user.id,
            RfpRun.state == "running",
            RfpRun.created_at > datetime.now(UTC) - STALE_AFTER,
        )
    )
    if busy:
        raise HTTPException(status.HTTP_409_CONFLICT, "you already have a run in progress")

    data = await _read_body(request)
    magic = ALLOWED_SUFFIXES[suffix]
    if not data or (magic is not None and not data.startswith(magic)):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "the file is not a valid file")

    def read_and_start():
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / f"upload{suffix}"
            path.write_bytes(data)
            return read_rfp(path)

    try:
        parsed = await run_in_threadpool(read_and_start)
    except NoRequirements:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no requirements found") from None
    except Exception:
        log.exception("could not read an uploaded RFP")
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "could not read the file"
        ) from None

    rfp_name = Path(filename).stem.split("_", 1)[0][:80]
    started = start_run(db, user, parsed, rfp_name, filename, request_id)
    db.commit()
    background.add_task(
        executor, factory, user.id, started.run.id, started.requirements, request_id
    )
    return started.run


@router.get("/runs", response_model=list[RunOut])
def list_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(RfpRun).where(RfpRun.created_by == user.id).order_by(RfpRun.created_at.desc())
    ).all()


@router.get("/runs/{run_id}", response_model=RunDetail)
def run_detail(
    run_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    run = _owned_run(db, user, run_id)
    summary = run_summary(db, user, run_id)
    return RunDetail(
        **RunOut.model_validate(run).model_dump(), answered=summary["total"], summary=summary
    )


@router.get("/runs/{run_id}/results", response_model=list[ResultOut])
def results(
    run_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _owned_run(db, user, run_id)
    return list_results(db, user, run_id)


@router.post("/runs/{run_id}/results/{requirement_id}/review", response_model=ResultOut)
def review(
    run_id: uuid.UUID,
    requirement_id: str,
    body: ReviewIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = review_result(
            db, user, run_id, requirement_id, body.action, body.final_status, body.note
        )
    except RunNotFound:
        db.commit()
        raise _not_found() from None
    except ReviewError as problem:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(problem)) from None
    db.commit()
    return result


@router.get("/runs/{run_id}/export")
def export(
    run_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    try:
        name, data = export_run_csv(db, user, run_id)
    except RunNotFound:
        db.commit()
        raise _not_found() from None
    except ExportBlocked as problem:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(problem)) from None
    db.commit()
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )

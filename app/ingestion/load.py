"""Load the manifest documents into the database: one document row, its ACL rows and chunks.

Run it with:  uv run python -m app.ingestion.load
It is safe to run again: a document that is already loaded is replaced, never duplicated.
"""

import hashlib
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.policy_types import Resource
from app.core.db import SessionLocal
from app.corpus.manifest import ManifestEntry, load_manifest, to_resource
from app.ingestion.access import ChunkRow, build_chunk_rows
from app.ingestion.chunk import chunk_document
from app.ingestion.extract import extract
from app.ingestion.ocr import run_ocr
from app.models import Chunk, Document, DocumentACL, User
from app.models.enums import DocStatus

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
# Fixed, so a document gets the same id on every machine and after every database rebuild.
ID_NAMESPACE = uuid.UUID("6f1c2d3e-4b5a-4c7d-8e9f-0a1b2c3d4e5f")


@dataclass(frozen=True)
class IngestResult:
    doc_id: str
    outcome: str  # "created", "replaced" or "parse_failed"
    status: DocStatus
    sections: int
    passages: int
    ocr_chunks: int


def logical_id(entry: ManifestEntry) -> uuid.UUID:
    return uuid.uuid5(ID_NAMESPACE, entry.logical_key)


def document_id(entry: ManifestEntry) -> uuid.UUID:
    return uuid.uuid5(ID_NAMESPACE, f"{entry.logical_key}:v{entry.version}")


def _chunk_model(row: ChunkRow) -> Chunk:
    return Chunk(
        id=row.id,
        document_id=row.document_id,
        parent_id=row.parent_id,
        level=row.level,
        chunk_index=row.chunk_index,
        content=row.content,
        page=row.page,
        section=row.section,
        token_count=row.token_count,
        from_ocr=row.from_ocr,
        classification=row.classification,
        department=row.department,
        allowed_roles=list(row.allowed_roles),
        allowed_purposes=list(row.allowed_purposes),
        status=row.status,
        valid_until=row.valid_until,
    )


def _resource_for(entry: ManifestEntry, user_ids: dict[str, uuid.UUID]) -> Resource:
    try:
        return to_resource(entry, user_ids)
    except KeyError as error:
        raise ValueError(
            f"{entry.id}: the manifest names user {error} but they are not in the database. "
            "Run the user seed first."
        ) from error


def ingest_document(
    db: Session,
    entry: ManifestEntry,
    user_ids: dict[str, uuid.UUID],
    raw_dir: Path = RAW_DIR,
) -> IngestResult:
    path = raw_dir / entry.filename
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    resource = _resource_for(entry, user_ids)

    extracted = extract(path)
    if extracted.needs_ocr:
        extracted = run_ocr(path, extracted)
    drafts = [] if extracted.needs_ocr else chunk_document(extracted)

    # Fail closed: a file we could not read is stored as parse_failed and nothing can use it.
    parsed = bool(drafts)
    if not parsed:
        resource = replace(resource, status=DocStatus.PARSE_FAILED)

    doc_id = document_id(entry)
    document = db.get(Document, doc_id)
    outcome = "created" if document is None else "replaced"
    if document is None:
        document = Document(id=doc_id)
        db.add(document)
    else:
        db.execute(delete(Chunk).where(Chunk.document_id == doc_id))
        db.execute(delete(DocumentACL).where(DocumentACL.document_id == doc_id))

    document.logical_id = logical_id(entry)
    document.version = entry.version
    document.filename = entry.filename
    document.doc_type = entry.document_type
    document.department = resource.department
    document.classification = resource.classification
    document.allowed_roles = sorted(resource.allowed_roles)
    document.allowed_purposes = sorted(resource.allowed_purposes)
    document.status = resource.status
    document.valid_until = resource.valid_until
    document.storage_uri = f"data/raw/{entry.filename}"
    document.content_sha256 = sha256
    db.flush()

    for rule in resource.acl:
        db.add(
            DocumentACL(
                document_id=doc_id,
                subject_type=rule.subject_type,
                subject_id=rule.subject_id,
                effect=rule.effect,
            )
        )

    rows = build_chunk_rows(doc_id, resource, drafts)
    sections = [row for row in rows if row.level == "section"]
    passages = [row for row in rows if row.level == "passage"]
    db.add_all(_chunk_model(row) for row in sections)
    db.flush()  # a passage points at its section, so sections go in first
    db.add_all(_chunk_model(row) for row in passages)
    db.flush()

    return IngestResult(
        doc_id=entry.id,
        outcome=outcome if parsed else "parse_failed",
        status=resource.status,
        sections=len(sections),
        passages=len(passages),
        ocr_chunks=sum(row.from_ocr for row in rows),
    )


def ingest_all(db: Session, raw_dir: Path = RAW_DIR) -> list[IngestResult]:
    user_ids = {user.email: user.id for user in db.scalars(select(User))}
    return [ingest_document(db, entry, user_ids, raw_dir) for entry in load_manifest().documents]


def main() -> int:
    with SessionLocal() as db:
        try:
            results = ingest_all(db)
        except ValueError as error:
            db.rollback()
            print(f"stopped, nothing was saved: {error}")
            return 1
        db.commit()
    print(f"{'doc':8} {'outcome':12} {'status':12} {'sections':>8} {'passages':>8} {'ocr':>5}")
    for r in results:
        print(
            f"{r.doc_id:8} {r.outcome:12} {r.status.value:12} "
            f"{r.sections:>8} {r.passages:>8} {r.ocr_chunks:>5}"
        )
    print(
        f"total: {sum(r.sections for r in results)} sections, "
        f"{sum(r.passages for r in results)} passages"
    )
    return 1 if any(r.outcome == "parse_failed" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())

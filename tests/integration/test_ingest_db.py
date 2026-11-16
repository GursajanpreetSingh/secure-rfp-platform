import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from app.auth.seed import load_seed_users, seed_users
from app.corpus.manifest import load_manifest
from app.ingestion.load import document_id, ingest_document
from app.models import Chunk, Document, DocumentACL, User
from app.models.enums import AclEffect, Classification, DocStatus, SubjectType

pytestmark = pytest.mark.integration

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
ENTRIES = {entry.id: entry for entry in load_manifest().documents}
PASSWORD = "test-password-123456"


@pytest.fixture
def user_ids(db_session):
    """Demo users in the database. Everything is rolled back when the test ends."""
    db_session.execute(delete(Document))  # start empty, even if the real data is loaded
    seed_users(db_session, load_seed_users(), PASSWORD)
    return {user.email: user.id for user in db_session.scalars(select(User))}


def _chunks(db, doc_id):
    return list(db.scalars(select(Chunk).where(Chunk.document_id == doc_id)))


def test_document_and_chunks_are_stored(db_session, user_ids):
    entry = ENTRIES["DOC-004"]
    result = ingest_document(db_session, entry, user_ids, RAW)

    assert result.outcome == "created"
    document = db_session.get(Document, document_id(entry))
    assert document.filename == entry.filename
    assert document.status == DocStatus.ACTIVE
    assert document.content_sha256 and len(document.content_sha256) == 64
    chunks = _chunks(db_session, document.id)
    assert len(chunks) == result.sections + result.passages > 20


def test_every_chunk_has_its_documents_access_fields(db_session, user_ids):
    ingest_document(db_session, ENTRIES["DOC-001"], user_ids, RAW)
    document = db_session.get(Document, document_id(ENTRIES["DOC-001"]))
    chunks = _chunks(db_session, document.id)
    assert chunks
    for chunk in chunks:
        assert chunk.classification == document.classification
        assert chunk.department == document.department
        assert sorted(chunk.allowed_roles) == sorted(document.allowed_roles)
        assert sorted(chunk.allowed_purposes) == sorted(document.allowed_purposes)
        assert chunk.status == document.status
        assert chunk.valid_until == document.valid_until
        assert chunk.from_ocr is False


def test_passages_point_at_sections_of_the_same_document(db_session, user_ids):
    ingest_document(db_session, ENTRIES["DOC-005"], user_ids, RAW)
    doc_id = document_id(ENTRIES["DOC-005"])
    by_id = {c.id: c for c in _chunks(db_session, doc_id)}
    passages = [c for c in by_id.values() if c.level == "passage"]
    assert passages
    for passage in passages:
        parent = by_id[passage.parent_id]
        assert parent.level == "section"
        assert parent.section == passage.section


def test_explicit_grant_is_stored_on_the_document(db_session, user_ids):
    ingest_document(db_session, ENTRIES["DOC-013"], user_ids, RAW)
    doc_id = document_id(ENTRIES["DOC-013"])
    rules = list(db_session.scalars(select(DocumentACL).where(DocumentACL.document_id == doc_id)))
    assert len(rules) == 1
    assert rules[0].effect == AclEffect.ALLOW
    assert rules[0].subject_type == SubjectType.USER
    assert rules[0].subject_id == str(user_ids["cfo@meridian.test"])
    assert db_session.get(Document, doc_id).classification == Classification.RESTRICTED


def test_loading_twice_replaces_instead_of_duplicating(db_session, user_ids):
    entry = ENTRIES["DOC-013"]
    first = ingest_document(db_session, entry, user_ids, RAW)
    second = ingest_document(db_session, entry, user_ids, RAW)

    assert (first.outcome, second.outcome) == ("created", "replaced")
    assert (first.sections, first.passages) == (second.sections, second.passages)
    doc_id = document_id(entry)
    assert len(_chunks(db_session, doc_id)) == second.sections + second.passages
    assert db_session.scalar(select(func.count()).select_from(Document)) == 1
    acl_count = db_session.scalar(
        select(func.count()).select_from(DocumentACL).where(DocumentACL.document_id == doc_id)
    )
    assert acl_count == 1


def test_document_ids_are_stable() -> None:
    assert document_id(ENTRIES["DOC-001"]) == document_id(ENTRIES["DOC-001"])
    assert document_id(ENTRIES["DOC-001"]) != document_id(ENTRIES["DOC-008"])
    assert isinstance(document_id(ENTRIES["DOC-001"]), uuid.UUID)


def test_unreadable_scan_fails_closed(db_session, user_ids, monkeypatch):
    monkeypatch.setattr("app.ingestion.load.run_ocr", lambda path, document: document)
    result = ingest_document(db_session, ENTRIES["DOC-009"], user_ids, RAW)

    assert result.outcome == "parse_failed"
    assert (result.sections, result.passages) == (0, 0)
    document = db_session.get(Document, document_id(ENTRIES["DOC-009"]))
    assert document.status == DocStatus.PARSE_FAILED
    assert _chunks(db_session, document.id) == []


def test_missing_user_stops_the_load(db_session, user_ids):
    without_cfo = {e: i for e, i in user_ids.items() if e != "cfo@meridian.test"}
    with pytest.raises(ValueError, match="user seed"):
        ingest_document(db_session, ENTRIES["DOC-013"], without_cfo, RAW)

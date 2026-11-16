import itertools
import uuid
from datetime import date
from functools import cache
from pathlib import Path

import pytest

from app.auth.policy import decide
from app.auth.policy_types import Subject
from app.auth.seed import load_seed_users
from app.corpus.manifest import load_manifest, to_resource
from app.ingestion.access import ChunkRow, build_chunk_rows, chunk_resource
from app.ingestion.chunk import chunk_document
from app.ingestion.extract import extract
from app.models.enums import Classification, Purpose, Role

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
ENTRIES = {entry.id: entry for entry in load_manifest().documents}
TEXT_DOCS = sorted(set(ENTRIES) - {"DOC-009"})  # the scan needs OCR; see test_ocr.py
USERS = load_seed_users()
USER_IDS = {u["email"]: uuid.uuid5(uuid.NAMESPACE_DNS, u["email"]) for u in USERS}
TODAYS = [date(2026, 11, 8), date(2026, 11, 16), date(2024, 6, 1)]


def _subject(user: dict) -> Subject:
    return Subject(
        id=USER_IDS[user["email"]],
        role=Role(user["role"]),
        department=user.get("department"),
        clearance=Classification(user["clearance"]),
        is_active=user.get("is_active", True),
    )


@cache
def _rows(doc_id: str) -> list[ChunkRow]:
    entry = ENTRIES[doc_id]
    drafts = chunk_document(extract(RAW / entry.filename))
    return build_chunk_rows(uuid.uuid4(), to_resource(entry, USER_IDS), drafts)


@pytest.mark.parametrize("doc_id", TEXT_DOCS)
def test_every_chunk_carries_its_documents_access_fields(doc_id: str) -> None:
    entry = ENTRIES[doc_id]
    rows = _rows(doc_id)
    assert rows
    for row in rows:
        assert row.classification == entry.classification
        assert row.department == entry.department
        assert set(row.allowed_roles) == entry.allowed_roles
        assert set(row.allowed_purposes) == entry.allowed_purposes
        assert row.status == entry.status
        assert row.valid_until == entry.valid_until


@pytest.mark.parametrize("doc_id", TEXT_DOCS)
def test_chunk_rows_link_up(doc_id: str) -> None:
    rows = _rows(doc_id)
    by_id = {row.id: row for row in rows}
    assert len(by_id) == len(rows)
    assert len({row.document_id for row in rows}) == 1
    for row in rows:
        if row.level == "section":
            assert row.parent_id is None
        else:
            parent = by_id[row.parent_id]
            assert parent.level == "section"
            assert parent.section == row.section


@pytest.mark.parametrize("doc_id", TEXT_DOCS)
def test_chunk_decisions_match_document_decisions(doc_id: str) -> None:
    """For every demo user, purpose and date, a chunk is allowed exactly when its document is."""
    document = to_resource(ENTRIES[doc_id], USER_IDS)
    rows = _rows(doc_id)
    sample = [rows[0], rows[len(rows) // 2], rows[-1]]
    for user, purpose, today in itertools.product(USERS, Purpose, TODAYS):
        subject = _subject(user)
        expected = decide(subject, document, purpose, today)
        for row in sample:
            actual = decide(subject, chunk_resource(row, document.acl), purpose, today)
            assert actual == expected, (doc_id, user["email"], purpose, today)


def test_restricted_documents_keep_their_explicit_grant_outside_the_chunk() -> None:
    entry = ENTRIES["DOC-013"]
    document = to_resource(entry, USER_IDS)
    row = _rows("DOC-013")[0]
    assert row.classification == Classification.RESTRICTED
    cfo = _subject(next(u for u in USERS if u["email"].startswith("cfo@")))
    ceo = _subject(next(u for u in USERS if u["email"].startswith("ceo@")))
    today = date(2026, 11, 16)
    with_acl = chunk_resource(row, document.acl)
    without_acl = chunk_resource(row, ())
    assert decide(cfo, with_acl, Purpose.ENTERPRISE_QA, today).allowed
    assert not decide(cfo, without_acl, Purpose.ENTERPRISE_QA, today).allowed
    assert not decide(ceo, with_acl, Purpose.ENTERPRISE_QA, today).allowed


def test_a_chunk_pointing_at_a_missing_parent_is_rejected() -> None:
    drafts = chunk_document(extract(RAW / ENTRIES["DOC-014"].filename))
    broken = [d for d in drafts if d.level == "passage"]
    with pytest.raises(ValueError):
        build_chunk_rows(uuid.uuid4(), to_resource(ENTRIES["DOC-014"], USER_IDS), broken)


def test_rows_do_not_share_mutable_state_with_the_resource() -> None:
    resource = to_resource(ENTRIES["DOC-001"], USER_IDS)
    rows = _rows("DOC-001")
    assert isinstance(rows[0].allowed_roles, tuple)
    assert rows[0].allowed_roles == tuple(sorted(resource.allowed_roles))

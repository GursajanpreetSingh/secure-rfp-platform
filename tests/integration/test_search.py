import hashlib
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app.auth.policy import decide
from app.auth.policy_types import Subject
from app.auth.seed import load_seed_users, seed_users
from app.corpus.manifest import load_manifest, to_resource
from app.ingestion.load import ingest_document
from app.models import Document, User
from app.models.chunk import EMBEDDING_DIM
from app.models.enums import Purpose
from app.retrieval.embed_chunks import embed_missing
from app.retrieval.search import search

pytestmark = pytest.mark.integration

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
ENTRIES = {entry.id: entry for entry in load_manifest().documents}
LOADED = ["DOC-001", "DOC-004", "DOC-005", "DOC-006", "DOC-008", "DOC-013", "DOC-014"]
TODAY = date(2026, 11, 16)
QUESTIONS = [
    "What is the p95 response time at 5,000 concurrent users?",
    "How are data encrypted at rest and how often are keys rotated?",
    "What salary band applies to an engineer?",
    "What was the FY25 revenue and net margin?",
    "Is multi-factor authentication required for all staff?",
    "What is the disaster recovery time objective?",
]


class FakeEmbedder:
    """Fixed vectors made from a hash. Keyword search does the real work in these tests."""

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [digest[i % len(digest)] / 255 for i in range(EMBEDDING_DIM)]


@pytest.fixture
def world(db_session):
    """Some real documents loaded and embedded, plus every demo user as a Subject."""
    db_session.execute(delete(Document))
    seed_users(db_session, load_seed_users(), "test-password-123456")
    users = list(db_session.scalars(select(User)))
    user_ids = {user.email: user.id for user in users}
    for doc_id in LOADED:
        ingest_document(db_session, ENTRIES[doc_id], user_ids, RAW)
    embed_missing(db_session, FakeEmbedder())
    subjects = {
        user.email: Subject(
            id=user.id,
            role=user.role,
            department=user.department,
            clearance=user.clearance,
            is_active=user.is_active,
        )
        for user in users
    }
    return db_session, subjects, user_ids


def _ask(world, email, question, purpose=Purpose.RFP, top_k=30):
    db, subjects, _ = world
    return search(db, subjects[email], question, purpose, FakeEmbedder(), TODAY, top_k=top_k)


def test_every_hit_is_allowed_by_the_policy(world) -> None:
    """For every demo user, question and purpose: nothing comes back that decide() refuses."""
    _, subjects, user_ids = world
    resources = {
        entry.filename: to_resource(entry, user_ids)
        for entry in (ENTRIES[doc_id] for doc_id in LOADED)
    }
    returned = 0
    for email, subject in subjects.items():
        for purpose, question in ((p, q) for p in Purpose for q in QUESTIONS):
            for hit in _ask(world, email, question, purpose):
                returned += 1
                assert decide(subject, resources[hit.filename], purpose, TODAY).allowed, (
                    email,
                    purpose,
                    hit.filename,
                )
    assert returned > 100  # the loop must actually have checked something


def test_engineer_finds_the_load_test_result_but_sales_cannot(world) -> None:
    question = "p95 response time at 5,000 concurrent users"
    engineer = _ask(world, "eng@meridian.test", question)
    assert any(h.filename.startswith("DOC-004") and "300 ms" in h.content for h in engineer)
    sales = _ask(world, "sales@meridian.test", question)
    assert not any(h.filename.startswith("DOC-004") for h in sales)


def test_restricted_documents_need_their_explicit_grant(world) -> None:
    question = "FY25 revenue net profit margin"
    cfo = _ask(world, "cfo@meridian.test", question, Purpose.ENTERPRISE_QA)
    assert any(h.filename.startswith("DOC-013") for h in cfo)
    for email in ("ceo@meridian.test", "eng@meridian.test", "auditor@meridian.test"):
        hits = _ask(world, email, question, Purpose.ENTERPRISE_QA)
        assert not any(h.filename.startswith("DOC-013") for h in hits), email


def test_salary_bands_are_never_returned_to_anyone(world) -> None:
    """DOC-014 allows no purpose at all, so not even the HR head can reach it through search."""
    question = "salary band engineer E2 LPA"
    for email in world[1]:
        for purpose in Purpose:
            hits = _ask(world, email, question, purpose)
            assert not any(h.filename.startswith("DOC-014") for h in hits), (email, purpose)


def test_old_and_unapproved_versions_are_never_returned_for_rfps(world) -> None:
    hits = _ask(world, "eng@meridian.test", "multi-factor authentication administrators")
    assert hits
    assert not any(h.filename.startswith("DOC-008") for h in hits)  # superseded v1 policy


def test_admins_and_former_staff_get_nothing(world) -> None:
    for email in ("admin@meridian.test", "former@meridian.test"):
        for question in QUESTIONS:
            assert _ask(world, email, question) == []


def test_empty_or_wordless_questions_return_nothing_or_nothing_forbidden(world) -> None:
    assert _ask(world, "eng@meridian.test", "   ") == []
    for hit in _ask(world, "sales@meridian.test", "?!"):  # no keywords; only meaning search runs
        assert not hit.filename.startswith(("DOC-004", "DOC-013", "DOC-014"))


def test_results_are_ranked_and_describe_where_they_came_from(world) -> None:
    hits = _ask(world, "eng@meridian.test", "encryption at rest key rotation", top_k=8)
    assert 0 < len(hits) <= 8
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
    for hit in hits:
        assert hit.vector_rank is not None or hit.keyword_rank is not None
        assert hit.section and hit.content


def test_search_validates_its_limits(world) -> None:
    with pytest.raises(ValueError):
        _ask(world, "eng@meridian.test", "anything", top_k=0)

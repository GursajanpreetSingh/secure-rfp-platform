import hashlib
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from app.auth.seed import load_seed_users, seed_users
from app.corpus.manifest import load_manifest
from app.ingestion.load import document_id, ingest_document
from app.models import Chunk, Document, User
from app.models.chunk import EMBEDDING_DIM
from app.retrieval.embed_chunks import embed_missing

pytestmark = pytest.mark.integration

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
ENTRIES = {entry.id: entry for entry in load_manifest().documents}


class FakeEmbedder:
    """Gives every text a fixed vector derived from its hash. No model is needed."""

    def __init__(self) -> None:
        self.calls = 0

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [digest[i % len(digest)] / 255 for i in range(EMBEDDING_DIM)]


@pytest.fixture
def loaded(db_session):
    db_session.execute(delete(Document))
    seed_users(db_session, load_seed_users(), "test-password-123456")
    user_ids = {user.email: user.id for user in db_session.scalars(select(User))}
    ingest_document(db_session, ENTRIES["DOC-013"], user_ids, RAW)
    return document_id(ENTRIES["DOC-013"])


def _count(db, doc_id, **conditions):
    query = select(func.count()).select_from(Chunk).where(Chunk.document_id == doc_id)
    for column, value in conditions.items():
        query = query.where(getattr(Chunk, column) == value)
    return db.scalar(query)


def test_only_passages_get_embeddings(db_session, loaded):
    passages = _count(db_session, loaded, level="passage")
    embedded = embed_missing(db_session, FakeEmbedder(), batch_size=10)

    assert embedded == passages > 10
    with_vector = db_session.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.document_id == loaded, Chunk.embedding.is_not(None))
    )
    assert with_vector == passages
    sections_with_vector = db_session.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.level == "section", Chunk.embedding.is_not(None))
    )
    assert sections_with_vector == 0


def test_embeddings_have_the_right_size(db_session, loaded):
    embed_missing(db_session, FakeEmbedder())
    chunk = db_session.scalars(
        select(Chunk).where(Chunk.document_id == loaded, Chunk.level == "passage").limit(1)
    ).one()
    assert len(chunk.embedding) == EMBEDDING_DIM


def test_running_again_embeds_nothing_new(db_session, loaded):
    first = FakeEmbedder()
    embed_missing(db_session, first)
    second = FakeEmbedder()
    assert embed_missing(db_session, second) == 0
    assert second.calls == 0

"""Add embeddings to every passage chunk that does not have one yet.

Run it with:  uv run python -m app.retrieval.embed_chunks
Only passages are embedded. Sections give context and are found through their passages.
It is safe to run again: chunks that already have an embedding are skipped.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import Chunk
from app.retrieval.embedder import Embedder, get_embedder

BATCH_SIZE = 64


def embed_missing(
    db: Session,
    embedder: Embedder,
    batch_size: int = BATCH_SIZE,
    commit_each_batch: bool = False,
) -> int:
    """Embed passages that have no embedding. Returns how many were embedded."""
    total = 0
    while True:
        chunks = db.scalars(
            select(Chunk)
            .where(Chunk.level == "passage", Chunk.embedding.is_(None))
            .order_by(Chunk.document_id, Chunk.chunk_index)
            .limit(batch_size)
        ).all()
        if not chunks:
            return total
        vectors = embedder.embed_passages([chunk.content for chunk in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk.embedding = vector
        db.flush()
        if commit_each_batch:
            db.commit()
        total += len(chunks)
        print(f"embedded {total} passages", flush=True)


def main() -> int:
    with SessionLocal() as db:
        count = embed_missing(db, get_embedder(), commit_each_batch=True)
        db.commit()
        waiting = db.scalar(
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.level == "passage", Chunk.embedding.is_(None))
        )
    print(f"done: {count} embedded now, {waiting} passages still without an embedding")
    return 0 if not waiting else 1


if __name__ == "__main__":
    raise SystemExit(main())

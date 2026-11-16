"""Permission-aware hybrid search over passage chunks.

Two searches run in the database, one by meaning (vector) and one by keywords (full text).
Both apply the access condition from access_sql.py, so a chunk the user may not use is never
fetched, never ranked and never able to push another result up or down. The two result lists
are then merged with reciprocal rank fusion.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.policy_types import Subject
from app.models.enums import Purpose
from app.retrieval.access_sql import ACCESS_SQL, access_params
from app.retrieval.embedder import Embedder

RRF_K = 60  # the usual constant: it keeps one very high rank from outweighing everything
PER_RETRIEVER = 30
MAX_QUERY_TERMS = 24
MIN_TERM_LENGTH = 2
TERM = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-/]*[A-Za-z0-9]|[A-Za-z0-9]")

VECTOR_SQL = f"""
SELECT ch.id
FROM chunks ch
WHERE ch.level = 'passage'
  AND ch.embedding IS NOT NULL
  AND {ACCESS_SQL}
ORDER BY ch.embedding <=> CAST(:qvec AS vector), ch.id
LIMIT :n
"""

KEYWORD_SQL = f"""
SELECT ch.id
FROM chunks ch, to_tsquery('english', :tsquery) AS q(query)
WHERE ch.level = 'passage'
  AND ch.tsv @@ q.query
  AND {ACCESS_SQL}
ORDER BY ts_rank_cd(ch.tsv, q.query) DESC, ch.id
LIMIT :n
"""

# The access condition is applied a second time here, so even a bug in an earlier step
# could not put a forbidden chunk into the final answer.
DETAIL_SQL = f"""
SELECT ch.id, ch.document_id, d.filename, ch.section, ch.page, ch.content, ch.from_ocr
FROM chunks ch
JOIN documents d ON d.id = ch.document_id
WHERE ch.id = ANY(CAST(:ids AS uuid[]))
  AND {ACCESS_SQL}
"""


@dataclass(frozen=True)
class SearchHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    section: str | None
    page: int | None
    content: str
    from_ocr: bool
    score: float
    vector_rank: int | None  # 1 = best match by meaning, None = not in that list
    keyword_rank: int | None


def build_tsquery(question: str) -> str | None:
    """Turn a question into a full-text query that matches any of its words.

    Each word is quoted, so characters such as '-' or '&' cannot break the query.
    Returns None when the question has no usable words.
    """
    seen: dict[str, None] = {}
    for word in TERM.findall(question.lower()):
        if len(word) >= MIN_TERM_LENGTH:
            seen.setdefault(word, None)
    terms = list(seen)[:MAX_QUERY_TERMS]
    if not terms:
        return None
    return " | ".join(f"'{term}'" for term in terms)


def fuse_rankings(
    vector_ids: list[str], keyword_ids: list[str], k: int = RRF_K
) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: each list gives 1/(k + rank) to every chunk it contains."""
    scores: dict[str, float] = {}
    for ranking in (vector_ids, keyword_ids):
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.7f}" for value in vector) + "]"


def search(
    db: Session,
    subject: Subject,
    question: str,
    purpose: Purpose,
    embedder: Embedder,
    today: date | None = None,
    top_k: int = 8,
    per_retriever: int = PER_RETRIEVER,
) -> list[SearchHit]:
    """The best passages this user may use for this purpose, most relevant first."""
    if top_k < 1 or per_retriever < 1:
        raise ValueError("top_k and per_retriever must be at least 1")
    question = question.strip()
    if not question:
        return []
    access = access_params(subject, purpose, today or date.today())

    by_meaning = db.execute(
        text(VECTOR_SQL),
        {**access, "qvec": _vector_literal(embedder.embed_query(question)), "n": per_retriever},
    )
    vector_ids = [str(row[0]) for row in by_meaning]

    keyword_ids: list[str] = []
    tsquery = build_tsquery(question)
    if tsquery is not None:
        by_keyword = db.execute(
            text(KEYWORD_SQL), {**access, "tsquery": tsquery, "n": per_retriever}
        )
        keyword_ids = [str(row[0]) for row in by_keyword]

    fused = fuse_rankings(vector_ids, keyword_ids)[:top_k]
    if not fused:
        return []
    rows = db.execute(text(DETAIL_SQL), {**access, "ids": [chunk_id for chunk_id, _ in fused]})
    details = {str(row.id): row for row in rows}

    hits = []
    for chunk_id, score in fused:
        row = details.get(chunk_id)
        if row is None:  # the second access check refused it
            continue
        hits.append(
            SearchHit(
                chunk_id=row.id,
                document_id=row.document_id,
                filename=row.filename,
                section=row.section,
                page=row.page,
                content=row.content,
                from_ocr=row.from_ocr,
                score=score,
                vector_rank=vector_ids.index(chunk_id) + 1 if chunk_id in vector_ids else None,
                keyword_rank=keyword_ids.index(chunk_id) + 1 if chunk_id in keyword_ids else None,
            )
        )
    return hits

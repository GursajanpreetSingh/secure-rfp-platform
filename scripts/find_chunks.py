"""Find where a phrase lives in the stored chunks, and (optionally) how a search ranks it.

    uv run python -m scripts.find_chunks --phrase "people build and support"
    uv run python -m scripts.find_chunks --phrase "people build and support" \\
        --query "The vendor shall employ at least 200 people."

This reads the whole chunk table without any permission filter, so it is a developer tool for
debugging retrieval. It is not part of the product and must never be exposed through the API.
"""

import argparse

from sqlalchemy import select, text

from app.auth.policy_types import Subject
from app.core.db import SessionLocal
from app.models import User
from app.models.enums import Purpose
from app.retrieval.embedder import get_embedder
from app.retrieval.search import search

SQL = text(
    """
    SELECT ch.id, d.filename, ch.level, ch.page, ch.section, ch.status,
           ch.embedding IS NOT NULL AS has_embedding, length(ch.content) AS chars,
           position(lower(:phrase) in lower(ch.content)) AS at
    FROM chunks ch JOIN documents d ON d.id = ch.document_id
    WHERE ch.content ILIKE :pattern
    ORDER BY d.filename, ch.page NULLS LAST, ch.chunk_index
    """
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--phrase", required=True, help="text to look for inside chunks")
    parser.add_argument("--query", help="also rank this question as the user would ask it")
    parser.add_argument("--as", dest="email", default="eng@meridian.test")
    parser.add_argument("--depth", type=int, default=100, help="how far down to look")
    args = parser.parse_args()

    with SessionLocal() as db:
        rows = db.execute(SQL, {"phrase": args.phrase, "pattern": f"%{args.phrase}%"}).all()
        print(f"{len(rows)} chunk(s) contain {args.phrase!r}\n")
        for row in rows:
            print(
                f"  {row.filename.split('_', 1)[0]} p{row.page} {row.level:<8} "
                f"embedded={row.has_embedding} status={row.status} chars={row.chars} "
                f"| {row.section}"
            )
        if not args.query:
            return 0

        user = db.scalar(select(User).where(User.email == args.email))
        subject = Subject(
            id=user.id,
            role=user.role,
            department=user.department,
            clearance=user.clearance,
            is_active=user.is_active,
        )
        hits = search(
            db,
            subject,
            args.query,
            Purpose.RFP,
            get_embedder(),
            top_k=args.depth,
            per_retriever=args.depth,
        )
        wanted = {row.id for row in rows}
        print(f"\nSearch for {args.query!r} as {args.email}, looking {args.depth} deep:")
        found = False
        for rank, hit in enumerate(hits, start=1):
            if hit.chunk_id in wanted:
                found = True
                print(
                    f"  overall #{rank}  vector#{hit.vector_rank} keyword#{hit.keyword_rank}  "
                    f"{hit.filename.split('_', 1)[0]} p{hit.page} | {hit.section}"
                )
        if not found:
            print(f"  not in the top {args.depth}, or you may not be allowed to see it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the compliance judge over one RFP, as one user, and print what came out.

    uv run python -m scripts.run_rfp --file path/to/RFP-B.pdf --as eng@meridian.test
    uv run python -m scripts.run_rfp --file ... --ids B-035,B-037 --verbose
    uv run python -m scripts.run_rfp --file ... --limit 5 --json run.json

Every requirement is searched with the permissions of the chosen user and written to the audit
log. Nothing is exported; this is for looking at results.
"""

import argparse
import json
import sys
import uuid
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from app.auth.policy_types import Subject
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.ingestion.extract import extract
from app.llm.client import build_llm
from app.models import User
from app.models.enums import Purpose
from app.retrieval.embedder import get_embedder
from app.retrieval.search import search
from app.rfp.assess import MAX_EVIDENCE, Assessment, ModelAsk, assess_rfp
from app.rfp.audit import audit_assessment, audit_suspicious
from app.rfp.parse import parse_rfp
from app.rfp.store import create_run, finish_run, save_assessment


def doc_code(filename: str) -> str:
    """DOC-005_support_policy.pdf -> DOC-005"""
    return filename.split("_", 1)[0]


def summarize(assessment: Assessment) -> dict:
    req, judgement = assessment.requirement, assessment.judgement
    row = {"id": req.id, "priority": req.priority, "section": req.section}
    if judgement is None:
        row.update(status="not_judged", reason=assessment.error, citations=[], rejected_quotes=[])
        return row
    row.update(
        status=judgement.status.value,
        reason=judgement.reason.value,
        downgraded_from=judgement.downgraded_from.value if judgement.downgraded_from else None,
        rejected_quotes=list(judgement.rejected_quotes),
        rationale=judgement.rationale,
        citations=[
            {"doc": doc_code(c.title), "page": c.page, "section": c.section, "quote": c.quote}
            for c in judgement.citations
        ],
    )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--file", required=True, type=Path, help="the RFP (pdf, docx or txt)")
    parser.add_argument("--as", dest="email", default="eng@meridian.test", help="who is asking")
    parser.add_argument("--ids", default="", help="only these requirement IDs, comma separated")
    parser.add_argument("--limit", type=int, default=0, help="only the first N requirements")
    parser.add_argument("--verbose", action="store_true", help="show rationale and quotes")
    parser.add_argument(
        "--top-k",
        type=int,
        default=MAX_EVIDENCE,
        help="excerpts retrieved and shown per requirement",
    )
    parser.add_argument("--hits", action="store_true", help="show which excerpts were retrieved")
    parser.add_argument("--json", type=Path, help="also save the results to this file")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}")
        return 1

    settings = get_settings()
    llm = build_llm(
        settings.llm_provider,
        settings.llm_api_key.get_secret_value(),
        settings.llm_models,
        settings.llm_timeout_ms,
    )
    embedder = get_embedder()
    rfp_name = args.file.stem.split("_", 1)[0]
    request_id = uuid.uuid4().hex[:16]

    parsed = parse_rfp(extract(args.file))
    requirements = parsed.requirements
    if args.ids:
        wanted = {item.strip() for item in args.ids.split(",") if item.strip()}
        requirements = [r for r in requirements if r.id in wanted]
    if args.limit:
        requirements = requirements[: args.limit]

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email))
        if user is None:
            print(f"No user {args.email}. Run the seed step first.")
            return 1
        subject = Subject(
            id=user.id,
            role=user.role,
            department=user.department,
            clearance=user.clearance,
            is_active=user.is_active,
        )
        found, running = len(parsed.requirements), len(requirements)
        print(f"{rfp_name}: {found} requirements found, running {running}")
        print(
            f"As {user.email} ({user.role.value}). Model calls can take a while on the free tier.\n"
        )
        for warning in parsed.warnings:
            print(f"  parser warning: {warning}")
        if parsed.suspicious:
            print(f"  {len(parsed.suspicious)} suspicious passage(s) kept out of the run (audited)")
            audit_suspicious(db, user, rfp_name, parsed.suspicious, request_id)

        run = create_run(
            db, user, rfp_name, args.file.name, len(requirements), parsed.warnings, request_id
        )
        rows: list[dict] = []

        def show(assessment: Assessment) -> None:
            audit_assessment(db, user, rfp_name, assessment, request_id, run.id)
            save_assessment(db, run, len(rows) + 1, assessment)
            row = summarize(assessment)
            rows.append(row)
            docs = ",".join(dict.fromkeys(c["doc"] for c in row["citations"])) or "-"
            note = f" (was {row['downgraded_from']})" if row.get("downgraded_from") else ""
            print(
                f"{row['id']:<7}{row['priority']:<10}{row['status']:<22}"
                f"{str(row['reason']):<22}{docs}{note}",
                flush=True,
            )
            if args.verbose and row["status"] != "not_judged":
                print(f"        why: {row['rationale']}")
                for quote in row["rejected_quotes"]:
                    print(f'        REJECTED quote: "{quote}"')
                for cite in row["citations"]:
                    print(f'        {cite["doc"]} p{cite["page"]}: "{cite["quote"]}"')

        def search_fn(question: str):
            hits = search(db, subject, question, Purpose.RFP, embedder, top_k=args.top_k)
            if args.hits:
                print(f"  retrieved for: {question[:70]}")
                for number, hit in enumerate(hits, start=1):
                    print(
                        f"    E{number} {doc_code(hit.filename)} p{hit.page} "
                        f"vector#{hit.vector_rank} keyword#{hit.keyword_rank} "
                        f"{(hit.section or '')[:40]}"
                    )
            return hits

        state = "failed"
        try:
            assess_rfp(requirements, search_fn, ModelAsk(llm), on_result=show, limit=args.top_k)
            state = "completed"
        finally:
            finish_run(db, user, run, state, request_id)
            db.commit()

    counts = Counter(row["status"] for row in rows)
    print("\nSummary: " + ", ".join(f"{name} {count}" for name, count in sorted(counts.items())))
    print(f"Saved as run {run.id}. Nothing is exportable until each answer is reviewed.")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"Saved {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

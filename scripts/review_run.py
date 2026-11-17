"""Look at a saved run, review its answers, and export it. A stand-in for the screen to come.

    uv run python -m scripts.review_run --run RUN_ID list
    uv run python -m scripts.review_run --run RUN_ID approve B-011 B-035
    uv run python -m scripts.review_run --run RUN_ID edit B-037 --status partial --note "why..."
    uv run python -m scripts.review_run --run RUN_ID reject B-040 --note "why..."
    uv run python -m scripts.review_run --run RUN_ID summary
    uv run python -m scripts.review_run --run RUN_ID export --out matrix.csv

It uses the same rules as the product: only the person who started the run can use it, and
export is refused while any answer is still pending.
"""

import argparse
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import User
from app.rfp.export import ExportBlocked, export_run_csv
from app.rfp.store import (
    ReviewError,
    RunNotFound,
    list_results,
    review_result,
    run_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--run", required=True, type=uuid.UUID)
    parser.add_argument("--as", dest="email", default="eng@meridian.test")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list")
    commands.add_parser("summary")
    approve = commands.add_parser("approve")
    approve.add_argument("ids", nargs="+")
    edit = commands.add_parser("edit")
    edit.add_argument("id")
    edit.add_argument("--status", required=True)
    edit.add_argument("--note", required=True)
    reject = commands.add_parser("reject")
    reject.add_argument("id")
    reject.add_argument("--note", required=True)
    export = commands.add_parser("export")
    export.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email))
        if user is None:
            print(f"No user {args.email}.")
            return 1
        code = 0
        try:
            if args.command == "list":
                for r in list_results(db, user, args.run):
                    final = r.final_status or "-"
                    print(f"{r.requirement_id:<7}{r.ai_status:<22}{r.review_state:<10}{final}")
            elif args.command == "summary":
                for key, value in run_summary(db, user, args.run).items():
                    print(f"{key}: {value}")
            elif args.command == "approve":
                for requirement_id in args.ids:
                    review_result(db, user, args.run, requirement_id, "approve")
                    print(f"{requirement_id}: approved")
            elif args.command == "edit":
                review_result(db, user, args.run, args.id, "edit", args.status, args.note)
                print(f"{args.id}: edited to {args.status}")
            elif args.command == "reject":
                review_result(db, user, args.run, args.id, "reject", note=args.note)
                print(f"{args.id}: rejected")
            else:
                name, data = export_run_csv(db, user, args.run)
                args.out.write_bytes(data)
                print(f"Wrote {args.out} ({len(data)} bytes). Suggested name: {name}")
        except (RunNotFound, ReviewError, ExportBlocked) as problem:
            print(f"Refused: {problem}")
            code = 2
        finally:
            db.commit()  # keeps the audit rows, including the refusals
    return code


if __name__ == "__main__":
    sys.exit(main())

"""Score the Q&A module on questions YOU wrote, as the users you name. Nothing is saved.

    uv run python -m scripts.eval_qa --file data/eval/qa_questions.yaml
    uv run python -m scripts.eval_qa --file ... --json out/qa_eval.json --verbose

Each question says who asks, what should happen, and (optionally) the words the answer must
contain and the only documents it may cite. A citation outside `allowed_docs` is a security
violation, counted separately from wrong answers.
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

LLM_PAUSE_SECONDS = 4  # the free tier limits how fast we may call


def doc_code(title: str) -> str:
    return title.split("_", 1)[0].strip()


def load_questions(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions") or []
    for number, item in enumerate(questions, start=1):
        for key in ("id", "as", "question", "expect"):
            if not item.get(key):
                raise ValueError(f"question {number} is missing '{key}'")
        if item["expect"] not in ("answer", "no_answer"):
            raise ValueError(f"{item['id']}: expect must be 'answer' or 'no_answer'")
    return questions


def judge(item: dict, status: str, text: str, docs: list[str]) -> dict:
    """Compare one result with what was expected. Pure, so it is unit tested."""
    problems: list[str] = []
    allowed = item.get("allowed_docs")
    violation = bool(allowed is not None and any(d not in allowed for d in docs))
    if violation:
        outside = sorted({d for d in docs if d not in allowed})
        problems.append(f"cited documents outside the allowed list: {', '.join(outside)}")
    if item["expect"] == "no_answer":
        if status != "no_answer":
            problems.append("should have said it could not find this, but answered")
    else:
        if status != "answered":
            problems.append("should have answered, but said it could not find it")
        else:
            if not docs:
                problems.append("answered without any cited document")
            lowered = text.lower()
            for needle in item.get("must_include") or []:
                if str(needle).lower() not in lowered:
                    problems.append(f"answer does not contain '{needle}'")
            for needle in item.get("must_not_include") or []:
                if str(needle).lower() in text.lower():
                    problems.append(f"answer contains '{needle}'")
    return {"passed": not problems, "violation": violation, "problems": problems}


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    return {
        "total": total,
        "passed": passed,
        "accuracy_pct": round(100 * passed / total, 1) if total else None,
        "violations": sum(1 for r in rows if r["violation"]),
    }


def main() -> int:
    import time

    from sqlalchemy import select

    from app.api.routes import qa as qa_routes
    from app.auth.policy_types import Subject
    from app.core.db import SessionLocal
    from app.models import User
    from app.qa import service

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--json", type=Path, help="also save the results here")
    parser.add_argument("--verbose", action="store_true", help="print each answer")
    args = parser.parse_args()

    try:
        questions = load_questions(args.file)
    except (OSError, ValueError, yaml.YAMLError) as problem:
        print(f"Cannot read the questions: {problem}")
        return 1
    if not questions:
        print("The file has no questions.")
        return 1

    backend = qa_routes.get_backend()
    rows: list[dict] = []
    with SessionLocal() as db:
        for item in questions:
            user = db.scalar(select(User).where(User.email == item["as"]))
            if user is None:
                print(f"{item['id']}: no such user {item['as']}")
                return 1
            subject = Subject(
                id=user.id,
                role=user.role,
                department=user.department,
                clearance=user.clearance,
                is_active=user.is_active,
            )
            try:
                answer, _, _ = service._run_model(
                    item["question"], [], backend.make_search(db, subject), backend.llm
                )
            except Exception as problem:  # report and carry on with the next question
                rows.append(
                    {
                        "id": item["id"],
                        "passed": False,
                        "violation": False,
                        "problems": [f"error: {type(problem).__name__}"],
                        "status": "error",
                        "docs": [],
                        "text": "",
                    }
                )
                print(f"{item['id']:<8}ERROR  {type(problem).__name__}")
                continue
            docs = list(dict.fromkeys(doc_code(c.title) for c in answer.citations))
            verdict = judge(item, answer.status.value, answer.text, docs)
            rows.append(
                {
                    "id": item["id"],
                    "as": item["as"],
                    "status": answer.status.value,
                    "docs": docs,
                    "text": answer.text,
                    **verdict,
                }
            )
            mark = (
                "PASS" if verdict["passed"] else ("VIOLATION" if verdict["violation"] else "FAIL")
            )
            print(f"{item['id']:<8}{mark:<10}{answer.status.value:<11}{','.join(docs) or '-'}")
            for line in verdict["problems"]:
                print(f"         - {line}")
            if args.verbose:
                print(f"         {answer.text[:300]}")
            sys.stdout.flush()
            time.sleep(LLM_PAUSE_SECONDS)
        db.rollback()  # nothing from an evaluation is kept

    summary = summarize(rows)
    print(
        f"\nSummary: {summary['passed']}/{summary['total']} correct "
        f"({summary['accuracy_pct']}%), security violations: {summary['violations']}"
    )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
        print(f"Saved to {args.json}")
    return 0 if summary["violations"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

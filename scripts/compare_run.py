"""Compare a saved run (from run_rfp --json) with the ground truth.

    uv run python -m scripts.compare_run --run run_a.json --rfp RFP-A
    uv run python -m scripts.compare_run --run run_b.json --rfp RFP-B --as eng@meridian.test

The ground truth is only read here. It is never given to the system under test.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

TRUTH = Path("data/rfps/ground_truth/rfp_ground_truth.yaml")
STATUSES = ["compliant", "partial", "non_compliant", "insufficient_evidence", "not_judged"]
CLAIMS = {"compliant", "partial", "non_compliant"}


def expected_for(item: dict, email: str) -> str:
    return item.get("expected_status_by_user", {}).get(email, item["expected_status"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--rfp", required=True, help="RFP-A or RFP-B")
    parser.add_argument("--as", dest="email", default="eng@meridian.test")
    parser.add_argument("--truth", type=Path, default=TRUTH)
    args = parser.parse_args()

    truth = yaml.safe_load(args.truth.read_text(encoding="utf-8"))
    block = next(item for item in truth["rfps"] if item["rfp"] == args.rfp)
    wanted = {item["id"]: item for item in block["requirements"]}
    visible = set(truth["visible_docs_for_rfp"].get(args.email, []))
    rows = {row["id"]: row for row in json.loads(args.run.read_text(encoding="utf-8"))}

    matrix: Counter = Counter()
    wrong: list[str] = []
    overclaims: list[str] = []
    leaks: list[str] = []
    hidden: list[str] = []
    for rid, item in wanted.items():
        row = rows.get(rid)
        if row is None:
            continue
        want, got = expected_for(item, args.email), row["status"]
        matrix[(want, got)] += 1
        cited = {c["doc"] for c in row["citations"]}
        if want != got:
            wrong.append(
                f"{rid}: expected {want}, got {got} ({row['reason']}); cited {sorted(cited)}"
            )
        if want == "insufficient_evidence" and got in CLAIMS:
            overclaims.append(f"{rid}: said {got} but evidence does not exist")
        for doc in cited & set(item.get("must_not_cite", [])):
            leaks.append(f"{rid}: cited {doc}, which must not be cited ({item.get('note', '')})")
        for doc in cited - visible:
            hidden.append(f"{rid}: cited {doc}, which this user may not see")

    total = len([r for r in wanted if r in rows])
    exact = sum(count for (want, got), count in matrix.items() if want == got)
    print(f"{args.rfp} as {args.email}: {exact}/{total} exact ({exact / total:.0%})")
    print("\nrows = expected, columns = got")
    short = {s: s[:6] for s in STATUSES}
    print(f"{'':<24}" + "".join(f"{short[s]:>8}" for s in STATUSES))
    for want in STATUSES[:4]:
        cells = "".join(f"{matrix[(want, got)]:>8}" for got in STATUSES)
        print(f"{want:<24}{cells}")

    def section(title: str, lines: list[str]) -> None:
        print(f"\n{title}: {len(lines)}")
        for line in lines:
            print("  " + line)

    section("SECURITY: cited a document that must not be cited", leaks)
    section("SECURITY: cited a document the user may not see", hidden)
    section("Claimed an answer where no evidence exists", overclaims)
    section("All differences from the ground truth", wrong)
    return 1 if leaks or hidden else 0


if __name__ == "__main__":
    sys.exit(main())

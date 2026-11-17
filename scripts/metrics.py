"""Score saved RFP runs against the ground truth: accuracy, precision, recall, F1 and error safety.

    uv run python -m scripts.metrics --run out/rfp_runs/run_a4.json:RFP-A \
        --run out/rfp_runs/run_b3.json:RFP-B --json eval/reports/rfp_metrics.json

The ground truth is only read here. It is never given to the system under test.
Errors are split into SAFE (the system said it could not decide) and UNSAFE (it stated a wrong
claim). For a compliance tool the unsafe errors are the ones that matter.
"""

import argparse
import json
from pathlib import Path

import yaml

TRUTH = Path("data/rfps/ground_truth/rfp_ground_truth.yaml")
CLASSES = ["compliant", "partial", "non_compliant", "insufficient_evidence"]
CLAIMS = {"compliant", "partial", "non_compliant"}
ABSTAIN = {"insufficient_evidence", "not_judged"}


def expected_for(item: dict, email: str) -> str:
    return item.get("expected_status_by_user", {}).get(email, item["expected_status"])


def ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def score(pairs: list[tuple[str, str]]) -> dict:
    """Pure scoring of (expected, got) pairs."""
    total = len(pairs)
    exact = sum(1 for want, got in pairs if want == got)
    per_class = {}
    f1s = []
    for cls in CLASSES:
        tp = sum(1 for w, g in pairs if w == cls and g == cls)
        fp = sum(1 for w, g in pairs if w != cls and g == cls)
        fn = sum(1 for w, g in pairs if w == cls and g != cls)
        precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
        f1 = (
            round(2 * precision * recall / (precision + recall), 3) if precision and recall else 0.0
        )
        if tp + fn:  # only classes that exist in the ground truth count towards the macro average
            f1s.append(f1)
        per_class[cls] = {
            "support": tp + fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    wrong = [(w, g) for w, g in pairs if w != g]
    unsafe = [(w, g) for w, g in wrong if g in CLAIMS]
    safe = [(w, g) for w, g in wrong if g in ABSTAIN]
    overclaims = [(w, g) for w, g in wrong if w == "insufficient_evidence" and g in CLAIMS]
    false_compliant = [(w, g) for w, g in wrong if g == "compliant"]
    return {
        "total": total,
        "exact": exact,
        "accuracy": ratio(exact, total),
        "macro_f1": round(sum(f1s) / len(f1s), 3) if f1s else None,
        "per_class": per_class,
        "errors": len(wrong),
        "unsafe_errors": len(unsafe),
        "safe_errors": len(safe),
        "overclaims_on_missing_evidence": len(overclaims),
        "false_compliant": len(false_compliant),
        "unsafe_error_rate": ratio(len(unsafe), total),
    }


def evaluate(rows: dict, block: dict, visible: set[str], email: str) -> dict:
    pairs, leaks, hidden = [], [], []
    for item in block["requirements"]:
        row = rows.get(item["id"])
        if row is None:
            continue
        pairs.append((expected_for(item, email), row["status"]))
        cited = {c["doc"] for c in row["citations"]}
        leaks += [item["id"] for doc in cited & set(item.get("must_not_cite", []))]
        hidden += [item["id"] for doc in cited - visible]
    result = score(pairs)
    result["security_violations"] = {
        "cited_forbidden": len(leaks),
        "cited_not_visible": len(hidden),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--run", action="append", required=True, help="FILE:RFP-A (repeatable)")
    parser.add_argument("--as", dest="email", default="eng@meridian.test")
    parser.add_argument("--truth", type=Path, default=TRUTH)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    truth = yaml.safe_load(args.truth.read_text(encoding="utf-8"))
    visible = set(truth["visible_docs_for_rfp"].get(args.email, []))
    report, all_pairs = {}, []
    for spec in args.run:
        path, _, rfp = spec.rpartition(":")
        block = next(item for item in truth["rfps"] if item["rfp"] == rfp)
        rows = {r["id"]: r for r in json.loads(Path(path).read_text(encoding="utf-8"))}
        report[rfp] = evaluate(rows, block, visible, args.email)
        all_pairs += [
            (expected_for(i, args.email), rows[i["id"]]["status"])
            for i in block["requirements"]
            if i["id"] in rows
        ]
    report["ALL"] = score(all_pairs)

    for name, res in report.items():
        print(
            f"\n{name}: {res['exact']}/{res['total']} correct, accuracy {res['accuracy']:.1%}, "
            f"macro-F1 {res['macro_f1']}"
        )
        print(
            f"  errors {res['errors']}: unsafe (wrong claim) {res['unsafe_errors']}, "
            f"safe (could not decide) {res['safe_errors']}"
        )
        print(
            f"  claimed something where evidence does not exist: "
            f"{res['overclaims_on_missing_evidence']}; marked compliant wrongly: "
            f"{res['false_compliant']}"
        )
        if "security_violations" in res:
            print(f"  security violations: {res['security_violations']}")
        print(f"  {'class':<24}{'support':>8}{'precision':>11}{'recall':>8}{'f1':>7}")
        for cls, m in res["per_class"].items():
            show = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
            print(
                f"  {cls:<24}{m['support']:>8}{show(m['precision']):>11}"
                f"{show(m['recall']):>8}{show(m['f1']):>7}"
            )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2))
        print(f"\nSaved to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

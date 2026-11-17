from scripts.metrics import evaluate, expected_for, ratio, score


def test_perfect_scores():
    out = score([("compliant", "compliant"), ("partial", "partial")])
    assert out["accuracy"] == 1.0 and out["unsafe_errors"] == 0 and out["macro_f1"] == 1.0


def test_unsafe_and_safe_errors_are_separated():
    pairs = [
        ("compliant", "compliant"),
        ("compliant", "insufficient_evidence"),  # safe: it declined
        ("partial", "compliant"),  # unsafe: wrong claim
        ("insufficient_evidence", "non_compliant"),  # unsafe overclaim
        ("compliant", "not_judged"),  # safe
    ]
    out = score(pairs)
    assert out["errors"] == 4 and out["safe_errors"] == 2 and out["unsafe_errors"] == 2
    assert out["overclaims_on_missing_evidence"] == 1 and out["false_compliant"] == 1


def test_precision_and_recall():
    pairs = [("compliant", "compliant"), ("partial", "compliant"), ("compliant", "partial")]
    c = score(pairs)["per_class"]["compliant"]
    assert c["precision"] == 0.5 and c["recall"] == 0.5 and c["f1"] == 0.5


def test_ratio_handles_zero():
    assert ratio(1, 0) is None and ratio(1, 2) == 0.5


def test_expected_for_user_override():
    item = {"expected_status": "compliant", "expected_status_by_user": {"a@b.c": "partial"}}
    assert expected_for(item, "a@b.c") == "partial" and expected_for(item, "x@y.z") == "compliant"


def test_security_violations_counted():
    block = {
        "requirements": [
            {"id": "R1", "expected_status": "compliant", "must_not_cite": ["DOC-003"]},
            {"id": "R2", "expected_status": "compliant"},
        ]
    }
    rows = {
        "R1": {"status": "compliant", "citations": [{"doc": "DOC-003"}]},
        "R2": {"status": "compliant", "citations": [{"doc": "DOC-009"}]},
    }
    out = evaluate(rows, block, {"DOC-005"}, "eng@meridian.test")
    assert out["security_violations"] == {"cited_forbidden": 1, "cited_not_visible": 2}

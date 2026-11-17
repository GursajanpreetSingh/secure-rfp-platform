import pytest

from scripts.eval_qa import doc_code, judge, load_questions, summarize


def item(**over):
    return {"id": "q", "as": "a@b.c", "question": "?", "expect": "answer", **over}


def test_doc_code():
    assert doc_code("DOC-005_support_policy.pdf") == "DOC-005"
    assert doc_code("Support policy") == "Support policy"


def test_good_answer_passes():
    out = judge(item(must_include=["24"]), "answered", "Support runs 24 hours.", ["DOC-005"])
    assert out["passed"] and not out["violation"]


def test_missing_words_fail():
    out = judge(item(must_include=["24"]), "answered", "Support is available.", ["DOC-005"])
    assert not out["passed"] and not out["violation"]


def test_answer_without_citation_fails():
    assert not judge(item(), "answered", "yes", [])["passed"]


def test_wrongly_declined_fails():
    assert not judge(item(), "no_answer", "could not find", [])["passed"]


def test_no_answer_expected():
    assert judge(item(expect="no_answer"), "no_answer", "x", [])["passed"]
    assert not judge(item(expect="no_answer"), "answered", "x", ["DOC-005"])["passed"]


def test_citation_outside_allowed_list_is_a_violation():
    out = judge(item(allowed_docs=["DOC-005"]), "answered", "ok", ["DOC-005", "DOC-003"])
    assert out["violation"] and not out["passed"]


def test_must_not_include():
    out = judge(item(must_not_include=["secret"]), "answered", "a secret", ["DOC-005"])
    assert not out["passed"]


def test_summary():
    rows = [{"passed": True, "violation": False}, {"passed": False, "violation": True}]
    assert summarize(rows) == {"total": 2, "passed": 1, "accuracy_pct": 50.0, "violations": 1}
    assert summarize([])["accuracy_pct"] is None


def test_load_questions_validates(tmp_path):
    good = tmp_path / "q.yaml"
    good.write_text("questions:\n  - {id: a, as: x@y.z, question: hi, expect: answer}\n")
    assert len(load_questions(good)) == 1
    bad = tmp_path / "bad.yaml"
    bad.write_text("questions:\n  - {id: a, as: x@y.z, question: hi, expect: maybe}\n")
    with pytest.raises(ValueError):
        load_questions(bad)
    missing = tmp_path / "m.yaml"
    missing.write_text("questions:\n  - {id: a}\n")
    with pytest.raises(ValueError):
        load_questions(missing)


def test_duplicate_ids_are_refused(tmp_path):
    path = tmp_path / "d.yaml"
    path.write_text(
        "questions:\n"
        "  - {id: a, as: x@y.z, question: hi, expect: answer}\n"
        "  - {id: a, as: x@y.z, question: ho, expect: answer}\n"
    )
    with pytest.raises(ValueError):
        load_questions(path)

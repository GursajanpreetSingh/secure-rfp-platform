from ui import format as fmt


def result(**over):
    base = {
        "requirement_id": "B-001",
        "position": 1,
        "ai_status": "compliant",
        "review_state": "pending",
        "final_status": None,
    }
    return {**base, **over}


def test_md_escape_neutralises_markdown_and_links():
    out = fmt.md_escape("**bold** [x](http://evil) <b>hi</b>\nnext")
    assert "**" not in out.replace("\\*", "")
    assert "\n" not in out
    assert "\\[" in out and "\\(" in out and "\\<" in out


def test_md_escape_handles_none():
    assert fmt.md_escape(None) == ""


def test_status_text_known_and_unknown():
    assert "Compliant" in fmt.status_text("compliant")
    assert fmt.status_text(None) == "-"
    assert "weird" in fmt.status_text("weird")


def test_short_time():
    assert fmt.short_time("2026-11-17T15:48:00Z") == "2026-11-17 15:48 UTC"
    assert fmt.short_time("not a date") == "-"
    assert fmt.short_time(None) == "-"


def test_chart_rows_order_and_skips_empty_and_unknown():
    rows = fmt.chart_rows({"partial": 2, "compliant": 5, "mystery": 9, "non_compliant": 0})
    assert list(rows) == ["Compliant", "Partial"]
    assert rows["Compliant"] == 5


def test_progress_fraction_is_clamped():
    assert fmt.progress_fraction(5, 10) == 0.5
    assert fmt.progress_fraction(3, 0) == 0.0
    assert fmt.progress_fraction(20, 10) == 1.0


def test_newest_first_and_running():
    runs = [
        {"id": "a", "created_at": "2026-11-01T00:00:00Z", "state": "completed"},
        {"id": "b", "created_at": "2026-11-02T00:00:00Z", "state": "running"},
    ]
    assert [r["id"] for r in fmt.newest_first(runs)] == ["b", "a"]
    assert fmt.any_running(runs)
    assert not fmt.any_running(runs[:1])


def test_shown_status_follows_review():
    assert fmt.shown_status(result()) == "compliant"
    edited = result(review_state="edited", final_status="partial")
    assert fmt.shown_status(edited) == "partial"
    assert fmt.shown_status(result(review_state="rejected")) is None


def test_filter_results_by_review_and_status_in_order():
    items = [
        result(requirement_id="B-002", position=2, ai_status="partial"),
        result(requirement_id="B-001", position=1),
        result(requirement_id="B-003", position=3, review_state="edited", final_status="partial"),
    ]
    assert [r["requirement_id"] for r in fmt.filter_results(items)] == ["B-001", "B-002", "B-003"]
    assert len(fmt.filter_results(items, review_state="pending")) == 2
    assert [r["requirement_id"] for r in fmt.filter_results(items, status="partial")] == [
        "B-002",
        "B-003",
    ]


def test_not_judged_cannot_be_approved():
    assert "approve" in fmt.allowed_actions(result())
    assert "approve" not in fmt.allowed_actions(result(ai_status="not_judged"))


def test_review_problem_matches_server_rules():
    assert fmt.review_problem("approve", None, "") is None
    assert fmt.review_problem("edit", None, "long enough note") is not None
    assert fmt.review_problem("edit", "partial", "short") is not None
    assert fmt.review_problem("edit", "partial", "long enough note") is None
    assert fmt.review_problem("reject", None, "   ") is not None
    assert fmt.review_problem("reject", None, "wrong requirement") is None


def test_upload_problem():
    assert fmt.upload_problem("rfp.pdf", 1000) is None
    assert fmt.upload_problem("RFP.DOCX", 1000) is None
    assert fmt.upload_problem("rfp.exe", 1000) is not None
    assert fmt.upload_problem("rfp", 1000) is not None
    assert fmt.upload_problem("rfp.pdf", 0) is not None
    assert fmt.upload_problem("rfp.pdf", fmt.MAX_UPLOAD_BYTES + 1) is not None

from ui import htmlkit as hk

SOURCES = [
    {"title": "DOC-005_support.pdf", "section": "SLA", "page": 2, "quote": 'Open "09:00" hours'},
    {"title": "DOC-007_cases.pdf", "section": None, "page": None, "quote": "Orion 2023"},
]


def test_esc_neutralises_markup_maths_and_emoji_codes():
    out = hk.esc('<script>alert(1)</script> $x$ :smile: "q"')
    assert "<script" not in out and "$" not in out and ":smile:" not in out
    assert "&lt;script&gt;" in out and "&quot;" in out


def test_esc_turns_newlines_into_breaks_but_attributes_stay_flat():
    assert hk.esc("a\nb") == "a<br>b"
    assert "<br>" not in hk.esc_attr("a\nb")


def test_user_bubble_escapes_the_question():
    out = hk.user_bubble("<img src=x onerror=alert(1)>")
    assert "<img" not in out and "onerror" in out and "&lt;img" in out
    assert "\n" not in out


def test_answer_card_layout_and_chips():
    out = hk.assistant_message(
        "answered", "Support is 9 to 6.\n- Mon to Fri\n- Not weekends", SOURCES
    )
    assert 'class="ans-head"' in out and "<li>Mon to Fri</li>" in out
    assert out.count('class="src-chip"') == 2 and "Based on 2 passages" in out
    assert (
        "DOC-005 &middot;" not in out and "DOC-005 &#183;" not in out
    )  # plain character, no entity
    assert "\n" not in out and "\n\n" not in out


def test_a_malicious_answer_cannot_inject_markup():
    out = hk.assistant_message(
        "answered",
        "<script>x</script>\n- [a](http://evil) <b>y</b>",
        [{"title": '"><i>', "quote": '"><b>'}],
    )
    for bad in ("<script", "<b>", "<i>"):
        assert bad not in out
    assert "&quot;&gt;&lt;b&gt;" in out  # the quote in the tooltip stays inside its attribute


def test_one_source_says_passage_not_passages():
    assert "Based on 1 passage<" in hk.assistant_message("answered", "Yes.", SOURCES[:1])


def test_no_answer_and_error_cards_are_friendly_and_fixed():
    assert "could not find this" in hk.assistant_message("no_answer", "ignored", [])
    assert "notice-warn" in hk.assistant_message("error", "ignored", [])
    assert "ignored" not in hk.assistant_message("no_answer", "ignored", [])


def test_redacted_notice_is_shown():
    out = hk.assistant_message("answered", "Yes.", [], redacted=True)
    assert "no longer available" in out

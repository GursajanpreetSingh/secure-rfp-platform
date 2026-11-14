from app.datagen import model as m
from app.datagen.quality import (
    check_claims,
    check_document,
    check_repetition,
    check_set_repetition,
)

LONG = "This paragraph has more than eight words so repetition rules apply to it."


def _doc(*blocks, title="Title") -> m.Document:
    return m.Document(title, "Sub", (("V", "1"),), (m.Section("S", tuple(blocks)),))


def test_clean_document_has_no_findings():
    assert check_document("DOC-001", _doc(m.Paragraph(LONG))) == []


def test_repetition_allows_two_copies_but_flags_three():
    two = _doc(m.Paragraph(LONG), m.Paragraph(LONG))
    three = _doc(m.Paragraph(LONG), m.Paragraph(LONG), m.Paragraph(LONG))
    assert check_repetition("DOC-001", two) == []
    findings = check_repetition("DOC-001", three)
    assert len(findings) == 1
    assert "3 copies" in findings[0].detail


def test_repetition_ignores_case_whitespace_and_short_lines():
    spaced = _doc(m.Paragraph(LONG), m.Paragraph(LONG.upper()), m.Paragraph("  " + LONG + "  "))
    assert len(check_repetition("DOC-001", spaced)) == 1
    short = _doc(*[m.Paragraph("See section three.")] * 5)
    assert check_repetition("DOC-001", short) == []


def test_repetition_sees_lists_notes_and_nested_sections():
    nested = m.Section("Inner", (m.BulletList((LONG, LONG)), m.Note(LONG)))
    doc = m.Document("T", "S", (("V", "1"),), (m.Section("Outer", (nested,)),))
    assert len(check_repetition("DOC-001", doc)) == 1


def test_forbidden_claim_flagged_outside_its_allowed_document():
    doc = _doc(m.Paragraph("We offer 24/7 support to every customer."))
    assert [f.kind for f in check_claims("DOC-005", doc)] == ["claim"]
    assert check_claims("DOC-011", doc) == []


def test_each_default_rule_fires():
    cases = [
        "Data is encrypted with AES-128 at rest.",
        "We can deploy on-premise for large clients.",
        "Our ISO 9001 certificate is currently valid.",
        "Round-the-clock support is available.",
    ]
    for text in cases:
        assert check_claims("DOC-001", _doc(m.Paragraph(text))), text


def test_expired_wording_is_not_flagged():
    doc = _doc(m.Paragraph("The ISO 9001 certificate expired on 31 December 2024."))
    assert check_claims("DOC-001", doc) == []


def test_claims_found_in_tables():
    doc = _doc(m.Table(("Item", "Value"), (("Support", "24/7 support"),)))
    assert check_claims("DOC-001", doc)


def test_set_repetition_counts_across_documents():
    docs = {f"DOC-{i}": _doc(m.Paragraph(LONG)) for i in range(4)}
    assert len(check_set_repetition(docs)) == 1
    assert check_set_repetition({k: docs[k] for k in list(docs)[:3]}) == []

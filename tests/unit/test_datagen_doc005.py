from collections.abc import Mapping

from app.datagen import model as m
from app.datagen.build import build_document
from app.datagen.docs.doc005 import build
from app.datagen.facts import load_facts
from app.datagen.manifest import load_manifest
from app.datagen.quality import check_document, prose_units


def _entry():
    docs = load_manifest().documents
    entries = docs.values() if isinstance(docs, Mapping) else docs
    return next(e for e in entries if e.id == "DOC-005")


def _doc():
    return build(load_facts(), _entry())


def _text():
    return " ".join(prose_units(_doc()))


def _tables(blocks):
    for block in blocks:
        if isinstance(block, m.Table):
            yield block
        elif isinstance(block, m.Section):
            yield from _tables(block.blocks)


def test_doc005_passes_the_quality_checks():
    assert check_document("DOC-005", _doc()) == []


def test_doc005_states_weekday_hours_and_no_weekend_cover():
    text = _text()
    assert "Mon-Fri 09:00-18:00 IST" in text
    assert "Support is not staffed on Saturdays or Sundays" in text
    assert "24/7" not in text


def test_doc005_states_the_sla_numbers_from_the_facts():
    text = _text()
    assert "within 1 hour of support time" in text
    assert "within 4 hours" in text
    assert "within 24 hours" in text
    assert "99.9 percent" in text
    assert "Sunday 02:00-04:00 IST" in text
    for credit in ("5", "10", "25"):
        assert f"{credit} percent of the monthly fee" in text


def test_doc005_has_the_number_of_severity_examples_in_the_facts():
    expected = load_facts().get("support_details.severity_examples_count")
    examples = [t for t in _tables(_doc().sections) if t.headers[:2] == ("No.", "Situation")]
    assert len(examples) == 1
    assert len(examples[0].rows) == expected


def test_doc005_meets_the_minimum_page_count(tmp_path):
    minimum = load_manifest().minimum_pages
    result = build_document(_entry(), _doc(), tmp_path, minimum)
    assert result.meets_minimum
    assert result.ok

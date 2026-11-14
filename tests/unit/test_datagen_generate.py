from datetime import date
from types import SimpleNamespace

import pytest

from app.datagen.common import standard_metadata
from app.datagen.facts import Facts, load_facts, long_date
from app.datagen.generate import format_report, generate
from app.datagen.registry import BUILDERS, load_all, register
from app.datagen.sample import sample_document


def _entry(doc_id="DOC-001", fmt="pdf"):
    return SimpleNamespace(
        id=doc_id,
        format=fmt,
        filename=f"{doc_id}.{fmt}",
        target_pages=22,
        version=2,
        classification="internal",
        status="active",
        department="security",
        document_date=date(2025, 1, 10),
        effective_date=date(2025, 1, 15),
    )


def _builder(facts, entry):
    return sample_document(40, 5)


def test_dotted_lookup_on_the_real_facts_file():
    facts = load_facts()
    assert facts.get("security.patch_sla_days.critical") == 7
    assert facts["certifications.CERT-ISO27001.expires"] == date(2027, 2, 28)
    assert facts.get("certifications.0.id") == "CERT-ISO27001"
    assert facts.get("architecture.components.0.name") == "Edge load balancer"
    assert facts.as_of == date(2026, 11, 8)


def test_missing_paths_raise_a_clear_error():
    with pytest.raises(KeyError, match="not found"):
        load_facts().get("security.nope")
    with pytest.raises(KeyError, match="not found"):
        Facts({"a": [1]}).get("a.5")


def test_long_date_has_no_leading_zero():
    assert long_date(date(2025, 1, 5)) == "5 January 2025"


def test_standard_metadata_block():
    rows = dict(standard_metadata(_entry()))
    assert rows["Document ID"] == "DOC-001"
    assert rows["Classification"] == "Internal"
    assert rows["Effective date"] == "15 January 2025"


def test_generate_builds_registered_documents_and_reports_the_rest(tmp_path):
    entries = [_entry("DOC-001"), _entry("DOC-002")]
    rows = generate(entries, {"DOC-001": _builder}, load_facts(), tmp_path, 20)
    assert rows[0].result is not None
    assert rows[0].result.ok
    assert rows[1].result is None
    report = format_report(rows)
    assert "OK" in report
    assert "no builder yet" in report


def test_generate_only_filters_by_id(tmp_path):
    entries = [_entry("DOC-001"), _entry("DOC-002")]
    rows = generate(entries, {}, load_facts(), tmp_path, 20, only={"DOC-002"})
    assert [r.doc_id for r in rows] == ["DOC-002"]


def test_register_rejects_duplicate_builders():
    register("DOC-TEST")(_builder)
    try:
        with pytest.raises(ValueError, match="duplicate"):
            register("DOC-TEST")(_builder)
    finally:
        BUILDERS.pop("DOC-TEST")


def test_load_all_returns_the_registry():
    assert load_all() is BUILDERS

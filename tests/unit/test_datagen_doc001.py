from collections.abc import Mapping

from app.datagen.docs.doc001 import build
from app.datagen.facts import load_facts
from app.datagen.manifest import load_manifest
from app.datagen.quality import check_document, prose_units


def _entry():
    docs = load_manifest().documents
    entries = docs.values() if isinstance(docs, Mapping) else docs
    return next(e for e in entries if e.id == "DOC-001")


def _doc():
    return build(load_facts(), _entry())


def test_doc001_passes_the_quality_checks():
    assert check_document("DOC-001", _doc()) == []


def test_doc001_sections_are_in_order():
    titles = [s.title for s in _doc().sections]
    assert titles[:7] == [
        "1. Document control",
        "2. Purpose and objectives",
        "3. Scope and applicability",
        "4. Definitions",
        "5. Security principles",
        "6. Roles and responsibilities",
        "7. Governance and risk management",
    ]


def test_doc001_states_the_facts_it_is_built_from():
    text = " ".join(prose_units(_doc()))
    assert "MCS-POL-001" in text
    assert "from 10 to 14 characters" in text
    assert "from 180 to 365 days" in text
    assert "15 January 2025" in text

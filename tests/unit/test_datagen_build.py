from collections.abc import Mapping

import pytest

from app.datagen.build import build_document
from app.datagen.manifest import load_manifest
from app.datagen.sample import sample_document


def _entries():
    docs = load_manifest().documents
    return list(docs.values()) if isinstance(docs, Mapping) else list(docs)


def _entry(doc_id):
    return next(e for e in _entries() if e.id == doc_id)


def test_sample_document_is_unique_and_claim_free(tmp_path):
    result = build_document(_entry("DOC-001"), sample_document(), tmp_path, 1)
    assert result.findings == ()
    assert result.ok


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e.id)
def test_every_manifest_entry_builds_in_its_own_format(tmp_path, entry):
    result = build_document(entry, sample_document(), tmp_path, 1)
    assert result.path.name == entry.filename
    assert result.path.exists()
    assert result.path.stat().st_size > 0


def test_short_document_fails_the_minimum_page_rule(tmp_path):
    minimum = load_manifest().minimum_pages
    result = build_document(_entry("DOC-001"), sample_document(), tmp_path, minimum)
    assert not result.meets_minimum
    assert not result.ok


@pytest.mark.parametrize("doc_id", ["DOC-001", "DOC-006", "DOC-014"])
def test_long_document_meets_the_minimum_in_every_format(tmp_path, doc_id):
    minimum = load_manifest().minimum_pages
    big = sample_document(sections=40, paragraphs_per_section=5)
    result = build_document(_entry(doc_id), big, tmp_path, minimum)
    assert result.meets_minimum
    assert result.ok

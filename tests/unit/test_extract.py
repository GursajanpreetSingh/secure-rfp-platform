from functools import cache
from pathlib import Path

import pytest

from app.corpus.manifest import load_manifest
from app.ingestion.extract import ExtractedDocument, extract, format_table

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
ENTRIES = {entry.id: entry for entry in load_manifest().documents}


@cache
def _doc(doc_id: str) -> ExtractedDocument:
    return extract(RAW / ENTRIES[doc_id].filename)


@pytest.mark.parametrize("doc_id", sorted(set(ENTRIES) - {"DOC-009"}))
def test_every_text_file_extracts_cleanly(doc_id: str) -> None:
    document = _doc(doc_id)
    assert len(document.text.split()) > 3000
    assert not document.needs_ocr
    assert "(cid:" not in document.text
    assert "**" not in document.text
    assert any(line.startswith("# ") for line in document.text.splitlines())


def test_scanned_document_is_flagged_for_ocr() -> None:
    document = _doc("DOC-009")
    assert document.needs_ocr
    assert all(page.needs_ocr and not page.text for page in document.pages)
    assert len(document.pages) >= 20


def test_pdf_pages_are_numbered_and_running_footer_removed() -> None:
    document = _doc("DOC-001")
    assert [p.number for p in document.pages] == list(range(1, len(document.pages) + 1))
    assert "Synthetic demo document" not in document.text
    assert "Page 4" not in document.text


def test_pdf_headings_are_marked_by_level() -> None:
    lines = _doc("DOC-004").text.splitlines()
    assert "# 1. Executive summary" in lines
    assert "## Think times" in lines


def test_pdf_table_numbers_are_not_lost() -> None:
    text = _doc("DOC-007").text
    assert "Project start year | 2023" in text
    assert "Project length: 12 months" in text


def test_pdf_table_rows_carry_their_column_names() -> None:
    text = _doc("DOC-004").text
    assert "Measure: p95 response time | Result at 5,000 users: 300 ms" in text


def test_docx_keeps_headings_and_table_rows() -> None:
    document = _doc("DOC-006")
    assert document.pages[0].number is None
    lines = document.text.splitlines()
    assert "# 1. Purpose and scope" in lines
    assert "## What the plan covers" in lines
    assert any(" | " in line for line in lines)


def test_txt_headings_and_tables() -> None:
    lines = _doc("DOC-014").text.splitlines()
    assert "# SALARY BANDS FY26" in lines
    assert "# 4. Summary table of all bands" in lines
    assert any(line.startswith("## 5.1.") for line in lines)
    assert any("Family: Engineering | Level: E2" in line for line in lines)
    assert not any(set(line) <= set("-+=| ") and line for line in lines)


def test_format_table_labels_wide_tables_only() -> None:
    wide = format_table([["Name", "Qty", "Unit"], ["bolt", "4", "pcs"]])
    assert wide == ["Name: bolt | Qty: 4 | Unit: pcs"]
    narrow = format_table([["Item", "Detail"], ["Industry", "Retail"]])
    assert narrow == ["Industry | Retail"]
    assert format_table([[None, ""]]) == []


def test_unsupported_type_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "x.csv"
    bad.write_text("a,b")
    with pytest.raises(ValueError):
        extract(bad)

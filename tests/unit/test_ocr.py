from pathlib import Path

import pytest

from app.ingestion.chunk import chunk_document
from app.ingestion.extract import ExtractedDocument, extract
from app.ingestion.ocr import ocr_available, run_ocr

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
SCAN = RAW / "DOC-009_iso9001_certification_package.pdf"

pytestmark = pytest.mark.skipif(not ocr_available(), reason="Tesseract is not installed")


@pytest.fixture(scope="module")
def scanned() -> ExtractedDocument:
    return run_ocr(SCAN, extract(SCAN))


def test_ocr_fills_every_scanned_page(scanned: ExtractedDocument) -> None:
    assert not scanned.needs_ocr
    assert scanned.from_ocr
    assert all(page.from_ocr and page.text for page in scanned.pages)


def test_ocr_reads_the_key_facts(scanned: ExtractedDocument) -> None:
    flat = " ".join(scanned.text.split())
    assert "CWC-QMS-2021-00233" in flat
    assert "31 December 2024" in flat
    assert len(flat.split()) > 3000


def test_ocr_removes_running_header_and_footer(scanned: ExtractedDocument) -> None:
    assert "Synthetic demo document" not in scanned.text
    later = "\n".join(page.text for page in scanned.pages[2:])
    assert "ISO 9001 Certification Package" not in later


def test_ocr_finds_headings(scanned: ExtractedDocument) -> None:
    headings = [line for line in scanned.text.splitlines() if line.startswith("# ")]
    assert len(headings) >= 15
    assert any("Process: Customer onboarding" in h for h in headings)


def test_ocr_chunks_are_flagged_and_sectioned(scanned: ExtractedDocument) -> None:
    chunks = chunk_document(scanned)
    assert len([c for c in chunks if c.level == "section"]) >= 15
    assert all(c.from_ocr for c in chunks)
    assert any("CWC-QMS-2021-00233" in c.content for c in chunks if c.level == "passage")


def test_text_documents_are_returned_unchanged() -> None:
    path = RAW / "DOC-001_information_security_policy_v2.pdf"
    document = extract(path)
    assert run_ocr(path, document) is document

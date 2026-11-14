"""Count (or estimate) the pages of a generated document.

PDF pages are exact (read from the file). DOCX pages are an estimate, because Word
decides the real layout when the file is opened. TXT pages are words / 500.
"""

import math
from dataclasses import dataclass
from pathlib import Path

from docx import Document as WordDocument
from docx.oxml.ns import qn
from pypdf import PdfReader

TXT_WORDS_PER_PAGE = 500
DOCX_WORDS_PER_PAGE = 600  # calibrated against LibreOffice renders of generated files
TABLE_ROW_COST = 10  # a table row takes about as much room as 10 words of prose
BLOCK_COST = 8  # spacing and heading overhead per paragraph


@dataclass(frozen=True)
class PageCount:
    pages: int
    exact: bool


def count_pdf_pages(path: Path) -> PageCount:
    return PageCount(len(PdfReader(str(path)).pages), exact=True)


def count_txt_pages(path: Path) -> PageCount:
    words = len(Path(path).read_text(encoding="utf-8").split())
    return PageCount(max(1, math.ceil(words / TXT_WORDS_PER_PAGE)), exact=False)


def _has_page_break(paragraph) -> bool:
    return any(br.get(qn("w:type")) == "page" for br in paragraph._p.iter(qn("w:br")))


def estimate_docx_pages(path: Path) -> PageCount:
    """Estimate pages: split the body at page breaks and size each piece by its text."""
    word = WordDocument(str(path))
    segments: list[float] = [0.0]
    for p in word.paragraphs:
        segments[-1] += len(p.text.split()) + BLOCK_COST
        if _has_page_break(p):
            segments.append(0.0)
    for table in word.tables:
        segments[-1] += TABLE_ROW_COST * len(table.rows)
        for row in table.rows:
            for cell in row.cells:
                segments[-1] += len(cell.text.split())
    pages = sum(max(1, math.ceil(w / DOCX_WORDS_PER_PAGE)) for w in segments if w > 0)
    return PageCount(pages, exact=False)


def count_pages(path: Path) -> PageCount:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return count_pdf_pages(path)
    if suffix == ".docx":
        return estimate_docx_pages(path)
    if suffix == ".txt":
        return count_txt_pages(path)
    raise ValueError(f"unsupported format: {suffix}")

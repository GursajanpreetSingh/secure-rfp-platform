"""OCR for scanned PDF pages (pages that have no text layer)."""

import os
import re
import shutil
import statistics
from pathlib import Path

import pypdfium2 as pdfium
import pytesseract
from pytesseract import Output

from app.ingestion.extract import MARGIN_SHARE, ExtractedDocument, ExtractedPage, heading_line

OCR_DPI = 200
OCR_LANGUAGE = "eng"
# A scanned line is a heading if it is this much taller than the typical line.
HEADING_HEIGHT_RATIO = 1.5
# Numbered headings such as "11.2 Process: Customer onboarding".
NUMBERED_HEADING = re.compile(r"^\d+(\.\d+)*\.?\s+[A-Z]")
MAX_HEADING_WORDS = 12
# Tesseract's usual place on Windows, used only if it is not on PATH.
WINDOWS_DEFAULT = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")


def _find_tesseract() -> str | None:
    configured = os.environ.get("TESSERACT_CMD")
    if configured:
        return configured
    if shutil.which("tesseract"):
        return None  # pytesseract finds it on PATH
    if WINDOWS_DEFAULT.exists():
        return str(WINDOWS_DEFAULT)
    return None


def ocr_available() -> bool:
    return bool(_find_tesseract()) or shutil.which("tesseract") is not None


def _is_heading(text: str, ratio: float) -> bool:
    words = len(text.split())
    if len(text) < 4 or words > MAX_HEADING_WORDS or text.endswith((".", ":")):
        return False
    return ratio >= HEADING_HEIGHT_RATIO or bool(NUMBERED_HEADING.match(text))


def _read_page(pdf: pdfium.PdfDocument, index: int) -> str:
    image = pdf[index].render(scale=OCR_DPI / 72).to_pil().convert("L")
    data = pytesseract.image_to_data(
        image, lang=OCR_LANGUAGE, config="--psm 6", output_type=Output.DICT
    )
    lines: dict[tuple[int, int, int], list[tuple[str, int, int]]] = {}
    for i, word in enumerate(data["text"]):
        if word.strip() and float(data["conf"][i]) > 0:
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append((word, data["height"][i], data["top"][i]))
    if not lines:
        return ""
    typical = statistics.median(h for words in lines.values() for _, h, _ in words)
    margin = image.height * MARGIN_SHARE
    out = []
    for words in lines.values():
        top = min(t for _, _, t in words)
        bottom = max(t + h for _, h, t in words)
        if top < margin or bottom > image.height - margin:
            continue  # running header or footer
        text = " ".join(w for w, _, _ in words)
        ratio = statistics.median(h for _, h, _ in words) / typical
        out.append(heading_line(text, 1) if _is_heading(text, ratio) else text)
    return "\n".join(out)


def run_ocr(path: Path, document: ExtractedDocument) -> ExtractedDocument:
    """Return the document with OCR text filled in for every page that needs it."""
    if not document.needs_ocr:
        return document
    command = _find_tesseract()
    if command:
        pytesseract.pytesseract.tesseract_cmd = command
    pdf = pdfium.PdfDocument(str(path))
    pages = [
        ExtractedPage(page.number, _read_page(pdf, page.number - 1), from_ocr=True)
        if page.needs_ocr and page.number is not None
        else page
        for page in document.pages
    ]
    return ExtractedDocument(pages=tuple(pages))

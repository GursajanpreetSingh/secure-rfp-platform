"""Turn a raw file (PDF, DOCX or TXT) into plain text, page by page.

Headings come out as lines that start with '#' (one '#' per level), and every table row
becomes one self-contained line, so later steps work the same for every file type.
Only extraction happens here. OCR, chunking and permissions come in later steps.
"""

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

# A PDF page with fewer characters than this has no usable text layer (a scan).
MIN_TEXT_CHARS = 30
# Text this close to the top or bottom edge of a PDF page is a running header or footer.
MARGIN_SHARE = 0.06
# A line is a heading if its text is this much larger than body text and it is bold.
HEADING_SIZE_RATIO = 1.25
LEVEL_ONE_RATIO = 1.5
CID = re.compile(r"\(cid:(\d+)\)")
TABLE_SEPARATOR = re.compile(r"^[-=+| ]+$")


@dataclass(frozen=True)
class ExtractedPage:
    number: int | None  # None for formats without fixed pages (DOCX, TXT)
    text: str
    needs_ocr: bool = False  # no text layer yet; run OCR
    from_ocr: bool = False  # text came from OCR, so it may contain reading errors


@dataclass(frozen=True)
class ExtractedDocument:
    pages: tuple[ExtractedPage, ...]

    @property
    def needs_ocr(self) -> bool:
        return any(page.needs_ocr for page in self.pages)

    @property
    def from_ocr(self) -> bool:
        return any(page.from_ocr for page in self.pages)

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text)


def heading_line(text: str, level: int) -> str:
    return f"{'#' * level} {text}"


def clean_cell(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def format_table(rows: list[list[str | None]]) -> list[str]:
    """One line per table row. Tables with 3+ columns repeat the column name in each row."""
    cleaned = [[clean_cell(cell) for cell in row] for row in rows]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return []
    header, body = cleaned[0], cleaned[1:]
    if not body:
        return [" | ".join(cell for cell in header if cell)]
    lines = []
    for row in body:
        if len(row) >= 3:
            parts = [f"{h}: {c}" if h else c for h, c in zip(header, row, strict=False) if c]
        else:
            parts = [c for c in row if c]
        if parts:
            lines.append(" | ".join(parts))
    return lines


# ---------------------------------------------------------------- PDF


def _fix_bullets(text: str) -> str:
    return CID.sub(lambda m: "-" if m.group(1) == "127" else "", text)


def _inside(char: dict, boxes: list[tuple[float, float, float, float]]) -> bool:
    x = (char["x0"] + char["x1"]) / 2
    y = (char["top"] + char["bottom"]) / 2
    return any(x0 <= x <= x1 and top <= y <= bottom for x0, top, x1, bottom in boxes)


def _line_heading_level(line: dict, body_size: float) -> int | None:
    chars = [c for c in line["chars"] if c["text"].strip()]
    if not chars:
        return None
    size = Counter(round(c["size"], 1) for c in chars).most_common(1)[0][0]
    bold = sum("bold" in c["fontname"].lower() for c in chars) > len(chars) / 2
    if not bold or size < body_size * HEADING_SIZE_RATIO:
        return None
    return 1 if size >= body_size * LEVEL_ONE_RATIO else 2


def _body_size(pdf: pdfplumber.PDF) -> float:
    sizes: Counter[float] = Counter()
    for page in pdf.pages:
        sizes.update(round(c["size"], 1) for c in page.chars if c["text"].strip())
    return sizes.most_common(1)[0][0] if sizes else 10.0


def _pdf_page_lines(page: pdfplumber.page.Page, body_size: float) -> tuple[list[str], bool]:
    all_text = "".join(c["text"] for c in page.chars).strip()
    if len(all_text) < MIN_TEXT_CHARS:
        return [], True
    tables = page.find_tables()
    boxes = [t.bbox for t in tables]
    outside = page.filter(lambda o: o.get("object_type") != "char" or not _inside(o, boxes))
    margin = page.height * MARGIN_SHARE
    items: list[tuple[float, list[str]]] = []
    for line in outside.extract_text_lines():
        if line["top"] < margin or line["bottom"] > page.height - margin:
            continue
        text = _fix_bullets(line["text"]).strip()
        if not text:
            continue
        level = _line_heading_level(line, body_size)
        items.append((line["top"], [heading_line(text, level) if level else text]))
    for table in tables:
        rows = [[_fix_bullets(c or "") for c in row] for row in table.extract()]
        items.append((table.bbox[1], format_table(rows)))
    items.sort(key=lambda item: item[0])
    return [line for _, lines in items for line in lines], False


def _extract_pdf(path: Path) -> ExtractedDocument:
    pages = []
    with pdfplumber.open(str(path)) as pdf:
        body_size = _body_size(pdf)
        for number, page in enumerate(pdf.pages, start=1):
            lines, scanned = _pdf_page_lines(page, body_size)
            pages.append(ExtractedPage(number, "\n".join(lines), needs_ocr=scanned))
    return ExtractedDocument(pages=tuple(pages))


# ---------------------------------------------------------------- DOCX


def _docx_table_lines(table: Table) -> list[str]:
    rows = []
    for row in table.rows:
        cells: list[str | None] = []
        for cell in row.cells:
            value = clean_cell(cell.text)
            if not cells or value != cells[-1]:  # merged cells repeat their text
                cells.append(value)
        rows.append(cells)
    return format_table(rows)


def _docx_heading_level(style_name: str) -> int | None:
    if style_name == "Title":
        return 1
    match = re.fullmatch(r"Heading (\d)", style_name)
    return int(match.group(1)) if match else None


def _extract_docx(path: Path) -> ExtractedDocument:
    document = Document(str(path))
    lines: list[str] = []
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            level = _docx_heading_level(paragraph.style.name if paragraph.style else "")
            lines.append(heading_line(text, level) if level else text)
        elif tag == "tbl":
            lines.extend(_docx_table_lines(Table(child, document)))
    return ExtractedDocument(pages=(ExtractedPage(number=None, text="\n".join(lines)),))


# ---------------------------------------------------------------- TXT


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.split("|")]


def _extract_txt(path: Path) -> ExtractedDocument:
    raw = [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()]
    lines: list[str] = []
    i = 0
    while i < len(raw):
        line = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else ""
        if not line.strip():
            i += 1
        elif "|" in line and "+" in nxt and TABLE_SEPARATOR.match(nxt.strip()):
            rows = [_split_row(line)]
            i += 2
            while i < len(raw) and "|" in raw[i]:
                rows.append(_split_row(raw[i]))
                i += 1
            lines.extend(format_table(list(rows)))
        elif nxt.strip() and set(nxt.strip()) == {"="}:
            lines.append(heading_line(line.strip(), 1))
            i += 2
        elif nxt.strip() and set(nxt.strip()) == {"-"}:
            lines.append(heading_line(line.strip(), 2))
            i += 2
        else:
            lines.append(line.strip())
            i += 1
    return ExtractedDocument(pages=(ExtractedPage(number=None, text="\n".join(lines)),))


def extract(path: Path) -> ExtractedDocument:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".txt":
        return _extract_txt(path)
    raise ValueError(f"unsupported file type: {path.name}")

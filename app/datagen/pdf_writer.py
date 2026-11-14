"""Render a datagen Document to PDF with ReportLab.

Cover page, table of contents, running header/footer, page numbers, styled tables.
"""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageTemplate,
    Spacer,
    TableStyle,
)
from reportlab.platypus import PageBreak as RLPageBreak
from reportlab.platypus import Paragraph as RLParagraph
from reportlab.platypus import Table as RLTable
from reportlab.platypus.tableofcontents import TableOfContents

from app.datagen import model as m

INK = colors.HexColor("#1f2933")
ACCENT = colors.HexColor("#1d4e89")
LIGHT = colors.HexColor("#eef3f8")
GRID = colors.HexColor("#c5d0dc")

_base = getSampleStyleSheet()
BODY = ParagraphStyle(
    "Body",
    parent=_base["BodyText"],
    fontName="Helvetica",
    fontSize=10,
    leading=14.5,
    textColor=INK,
    spaceAfter=7,
)
H = {
    1: ParagraphStyle(
        "H1",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=21,
        textColor=ACCENT,
        spaceBefore=14,
        spaceAfter=9,
    ),
    2: ParagraphStyle(
        "H2",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=ACCENT,
        spaceBefore=11,
        spaceAfter=6,
    ),
    3: ParagraphStyle(
        "H3",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=INK,
        spaceBefore=8,
        spaceAfter=4,
    ),
}
COVER_TITLE = ParagraphStyle(
    "CoverTitle",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=28,
    leading=34,
    textColor=ACCENT,
    spaceAfter=10,
)
COVER_SUB = ParagraphStyle(
    "CoverSub", parent=BODY, fontSize=14, leading=19, textColor=INK, spaceAfter=24
)
CELL = ParagraphStyle("Cell", parent=BODY, fontSize=8.5, leading=11, spaceAfter=0)
CELL_HEAD = ParagraphStyle(
    "CellHead", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white
)
CAPTION = ParagraphStyle(
    "Caption",
    parent=BODY,
    fontName="Helvetica-Oblique",
    fontSize=8.5,
    leading=11,
    alignment=TA_CENTER,
    spaceBefore=3,
)
NOTE = ParagraphStyle(
    "Note",
    parent=BODY,
    backColor=LIGHT,
    borderColor=ACCENT,
    borderWidth=0.5,
    borderPadding=6,
    leftIndent=8,
    rightIndent=8,
    spaceBefore=6,
    spaceAfter=12,
)
LIST_ITEM = ParagraphStyle("ListItem", parent=BODY, leftIndent=16, bulletIndent=4, spaceAfter=3)
TOC_STYLES = [
    ParagraphStyle("TOC1", parent=BODY, fontName="Helvetica-Bold", leftIndent=0, spaceAfter=3),
    ParagraphStyle("TOC2", parent=BODY, leftIndent=14, fontSize=9.5, spaceAfter=2),
    ParagraphStyle("TOC3", parent=BODY, leftIndent=28, fontSize=9, spaceAfter=1),
]


class _Heading(RLParagraph):
    """A heading paragraph that tells the table of contents where it landed."""

    def __init__(self, text: str, level: int):
        super().__init__(escape(text), H[min(level, 3)])
        self.toc_level = min(level, 3) - 1
        self.toc_text = text


class _DocTemplate(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, _Heading):
            self.notify("TOCEntry", (flowable.toc_level, flowable.toc_text, self.page))


def _table(block: m.Table, width: float) -> list:
    ncols = len(block.headers)
    data = [[RLParagraph(escape(str(h)), CELL_HEAD) for h in block.headers]]
    for row in block.rows:
        data.append([RLParagraph(escape(str(c)), CELL) for c in row])
    table = RLTable(data, colWidths=[width / ncols] * ncols, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(2, len(data), 2):
        style.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    table.setStyle(TableStyle(style))
    parts: list = [table]
    if block.caption:
        parts.append(RLParagraph(escape(block.caption), CAPTION))
    parts.append(Spacer(1, 8))
    return parts


def _list(items, numbered: bool) -> list:
    out: list = []
    for i, item in enumerate(items, 1):
        bullet = f"{i}." if numbered else "\u2022"
        out.append(RLParagraph(escape(item), LIST_ITEM, bulletText=bullet))
    out.append(Spacer(1, 4))
    return out


def _blocks(blocks, level: int, width: float) -> list:
    out: list = []
    for b in blocks:
        if isinstance(b, m.Paragraph):
            out.append(RLParagraph(escape(b.text), BODY))
        elif isinstance(b, m.Note):
            out.append(RLParagraph(f"<b>{escape(b.label)}:</b> {escape(b.text)}", NOTE))
        elif isinstance(b, m.BulletList):
            out.extend(_list(b.items, False))
        elif isinstance(b, m.NumberedList):
            out.extend(_list(b.items, True))
        elif isinstance(b, m.Table):
            out.extend(_table(b, width))
        elif isinstance(b, m.PageBreak):
            out.append(RLPageBreak())
        elif isinstance(b, m.Section):
            out.append(_Heading(b.title, level + 1))
            out.extend(_blocks(b.blocks, level + 1, width))
        else:
            raise TypeError(f"unknown block type: {type(b).__name__}")
    return out


def write_pdf(doc: m.Document, path: Path) -> Path:
    """Write ``doc`` to ``path`` as a PDF and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    page_w, page_h = A4
    margin = 22 * mm
    width = page_w - 2 * margin

    def cover_page(canvas, _d):
        canvas.saveState()
        canvas.setFillColor(ACCENT)
        canvas.rect(0, page_h - 14 * mm, page_w, 14 * mm, stroke=0, fill=1)
        canvas.restoreState()

    def body_page(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(margin, page_h - 14 * mm, doc.title[:90])
        canvas.setStrokeColor(GRID)
        canvas.line(margin, page_h - 16 * mm, page_w - margin, page_h - 16 * mm)
        canvas.line(margin, 15 * mm, page_w - margin, 15 * mm)
        canvas.drawString(margin, 10 * mm, "Synthetic demo document")
        canvas.drawRightString(page_w - margin, 10 * mm, f"Page {d.page}")
        canvas.restoreState()

    body_frame = Frame(margin, 22 * mm, width, page_h - 44 * mm, id="body")
    cover_frame = Frame(margin, 30 * mm, width, page_h - 90 * mm, id="cover")
    tpl = _DocTemplate(
        str(path),
        pagesize=A4,
        title=doc.title,
        author="Synthetic generator",
        leftMargin=margin,
        rightMargin=margin,
    )
    tpl.addPageTemplates(
        [
            PageTemplate(id="cover", frames=[cover_frame], onPage=cover_page),
            PageTemplate(id="body", frames=[body_frame], onPage=body_page),
        ]
    )

    story: list = [
        Spacer(1, 40 * mm),
        RLParagraph(escape(doc.title), COVER_TITLE),
        RLParagraph(escape(doc.subtitle), COVER_SUB),
    ]
    meta = [
        [RLParagraph(f"<b>{escape(k)}</b>", CELL), RLParagraph(escape(v), CELL)]
        for k, v in doc.metadata
    ]
    if meta:
        meta_table = RLTable(meta, colWidths=[40 * mm, width - 40 * mm])
        meta_table.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, GRID),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(meta_table)
    story += [NextPageTemplate("body"), RLPageBreak(), RLParagraph("Contents", H[1])]
    toc = TableOfContents()
    toc.levelStyles = TOC_STYLES
    story += [toc, RLPageBreak()]
    for sec in doc.sections:
        story.append(_Heading(sec.title, 1))
        story.extend(_blocks(sec.blocks, 1, width))
    tpl.multiBuild(story)  # two passes, so the TOC knows the page numbers
    return path

"""Render a datagen Document to DOCX with python-docx (real heading styles)."""

from pathlib import Path

from docx import Document as WordDocument
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from app.datagen import model as m

ACCENT = RGBColor(0x1D, 0x4E, 0x89)


def _field(paragraph, instruction: str, placeholder: str = "") -> None:
    """Insert a Word field (TOC, PAGE...) that Word fills in when the file is opened."""
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = placeholder
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for el in (begin, instr, sep, text, end):
        run._r.append(el)


def _shade(cell, hex_fill: str) -> None:
    props = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    props.append(shd)


def _add_table(word, block: m.Table) -> None:
    table = word.add_table(rows=1, cols=len(block.headers))
    table.style = "Table Grid"
    for i, head in enumerate(block.headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(str(head))
        run.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        _shade(cell, "1D4E89")
    for row in block.rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = str(value)
    if block.caption:
        cap = word.add_paragraph()
        run = cap.add_run(block.caption)
        run.italic = True
        run.font.size = Pt(9)
    else:
        word.add_paragraph()


def _add_blocks(word, blocks, level: int) -> None:
    for b in blocks:
        if isinstance(b, m.Paragraph):
            word.add_paragraph(b.text)
        elif isinstance(b, m.Note):
            p = word.add_paragraph()
            p.paragraph_format.left_indent = Pt(14)
            label = p.add_run(f"{b.label}: ")
            label.bold = True
            label.font.color.rgb = ACCENT
            p.add_run(b.text).italic = True
        elif isinstance(b, m.BulletList):
            for item in b.items:
                word.add_paragraph(item, style="List Bullet")
        elif isinstance(b, m.NumberedList):
            for item in b.items:
                word.add_paragraph(item, style="List Number")
        elif isinstance(b, m.Table):
            _add_table(word, b)
        elif isinstance(b, m.PageBreak):
            word.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        elif isinstance(b, m.Section):
            word.add_heading(b.title, level=min(level + 1, 3))
            _add_blocks(word, b.blocks, level + 1)
        else:
            raise TypeError(f"unknown block type: {type(b).__name__}")


def write_docx(doc: m.Document, path: Path) -> Path:
    """Write ``doc`` to ``path`` as a DOCX and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    word = WordDocument()
    word.core_properties.title = doc.title
    word.core_properties.author = "Synthetic generator"

    word.add_paragraph(doc.title, style="Title")
    word.add_paragraph(doc.subtitle, style="Subtitle")
    for label, value in doc.metadata:
        p = word.add_paragraph()
        p.add_run(f"{label}: ").bold = True
        p.add_run(value)
    word.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    word.add_heading("Contents", level=1)
    _field(
        word.add_paragraph(),
        'TOC \\o "1-3" \\h \\z \\u',
        "Right-click and choose Update Field.",
    )
    word.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    for sec in doc.sections:
        word.add_heading(sec.title, level=1)
        _add_blocks(word, sec.blocks, 1)

    footer = word.sections[0].footer.paragraphs[0]
    footer.text = "Synthetic demo document - Page "
    _field(footer, "PAGE", "1")

    word.save(str(path))
    return path

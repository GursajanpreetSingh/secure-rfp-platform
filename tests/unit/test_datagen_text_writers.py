from docx import Document as WordDocument

from app.datagen import model as m
from app.datagen.docx_writer import write_docx
from app.datagen.txt_writer import render_txt, write_txt


def _doc() -> m.Document:
    sections = tuple(
        m.Section(
            f"Section {i}",
            (
                m.Paragraph("Text & <b> here. " * 20),
                m.BulletList(("a", "b")),
                m.NumberedList(("x", "y")),
                m.Note("careful"),
                m.Table(("A", "B"), (("1", "2"),), "cap"),
                m.PageBreak(),
                m.Section("Sub", (m.Paragraph("deep"),)),
            ),
        )
        for i in range(1, 4)
    )
    return m.Document("T", "S", (("Version", "1"),), sections)


def test_docx_uses_real_heading_styles_and_tables(tmp_path):
    path = write_docx(_doc(), tmp_path / "a.docx")
    word = WordDocument(str(path))
    headings = [
        (p.style.name, p.text) for p in word.paragraphs if p.style.name.startswith("Heading")
    ]
    assert ("Heading 1", "Section 2") in headings
    assert ("Heading 2", "Sub") in headings
    assert len(word.tables) == 3


def test_txt_numbers_sections_and_aligns_tables():
    text = render_txt(_doc())
    assert "2.1. Sub" in text
    assert "A | B" in text
    assert "Text & <b> here." in text


def test_txt_file_is_written_as_utf8(tmp_path):
    path = write_txt(_doc(), tmp_path / "a.txt")
    assert path.read_text(encoding="utf-8").startswith("T\n")

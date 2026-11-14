from pypdf import PdfReader

from app.datagen import model as m
from app.datagen.pdf_writer import write_pdf


def _sample_doc() -> m.Document:
    sections = tuple(
        m.Section(
            f"Section {i}",
            (
                m.Paragraph("Lorem ipsum & <b> dolor sit amet. " * 80),
                m.BulletList(("first", "second")),
                m.Note("be careful"),
                m.Table(("A", "B"), (("1", "2"), ("3", "4")), "A caption"),
                m.Section("Subsection", (m.Paragraph("filler text " * 400),)),
            ),
        )
        for i in range(1, 9)
    )
    return m.Document("Test Document", "A subtitle", (("Version", "1.0"),), sections)


def test_pdf_has_cover_toc_and_numbered_pages(tmp_path):
    path = write_pdf(_sample_doc(), tmp_path / "out.pdf")
    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() for page in reader.pages)

    assert len(reader.pages) >= 4
    assert "Test Document" in reader.pages[0].extract_text()
    assert "Contents" in text
    assert "Section 3" in text
    assert "Page 2" in text


def test_special_characters_do_not_break_rendering(tmp_path):
    doc = m.Document(
        "A & B <Co>",
        "sub",
        (("k", "v & w"),),
        (m.Section("S", (m.Paragraph("1 < 2 & 3 > 2"),)),),
    )
    assert write_pdf(doc, tmp_path / "x.pdf").stat().st_size > 1000

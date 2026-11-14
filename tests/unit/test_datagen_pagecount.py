import pytest
from pypdf import PdfReader

from app.datagen import model as m
from app.datagen.docx_writer import write_docx
from app.datagen.pagecount import count_pages
from app.datagen.pdf_writer import write_pdf


def _doc(sections: int) -> m.Document:
    secs = tuple(
        m.Section(f"Section {i}", (m.Paragraph("word " * 600),)) for i in range(1, sections + 1)
    )
    return m.Document("T", "S", (("Version", "1"),), secs)


def test_pdf_count_is_exact_and_matches_pypdf(tmp_path):
    path = write_pdf(_doc(6), tmp_path / "a.pdf")
    result = count_pages(path)
    assert result.exact is True
    assert result.pages == len(PdfReader(str(path)).pages)


def test_txt_counts_500_words_per_page(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("word " * 1000, encoding="utf-8")
    assert count_pages(path).pages == 2
    path.write_text("word " * 1001, encoding="utf-8")
    assert count_pages(path).pages == 3
    assert count_pages(path).exact is False


def test_docx_estimate_grows_with_content(tmp_path):
    small = count_pages(write_docx(_doc(3), tmp_path / "s.docx"))
    large = count_pages(write_docx(_doc(12), tmp_path / "l.docx"))
    assert small.exact is False
    assert small.pages >= 3
    assert large.pages > small.pages + 4


def test_unsupported_extension_is_rejected(tmp_path):
    path = tmp_path / "a.xml"
    path.write_text("<a/>")
    with pytest.raises(ValueError, match="unsupported"):
        count_pages(path)

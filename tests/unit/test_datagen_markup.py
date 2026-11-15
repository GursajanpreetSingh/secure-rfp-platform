import pytest

from app.datagen import model as m
from app.datagen.markup import blocks, section


def test_paragraph_wrapped_over_lines_is_joined():
    result = blocks("First line of the paragraph\n  continues here.\n\nSecond paragraph.")
    assert result == (
        m.Paragraph("First line of the paragraph continues here."),
        m.Paragraph("Second paragraph."),
    )


def test_bullets_and_numbered_lists_keep_wrapped_lines_together():
    result = blocks("- first item that\n  wraps\n- second\n\n1. one\n2. two\n  more")
    assert result[0] == m.BulletList(("first item that wraps", "second"))
    assert result[1] == m.NumberedList(("one", "two more"))


def test_notes_keep_their_label():
    result = blocks("NOTE: be careful.\n\nIMPORTANT: really careful.\n\nWARNING: stop.")
    assert result == (
        m.Note("be careful.", "Note"),
        m.Note("really careful.", "Important"),
        m.Note("stop.", "Warning"),
    )


def test_table_with_separator_and_caption():
    text = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\nCaption: Two rows"
    assert blocks(text) == (m.Table(("A", "B"), (("1", "2"), ("3", "4")), "Two rows"),)


def test_table_without_data_rows_is_rejected():
    with pytest.raises(ValueError, match="header row"):
        blocks("| A | B |\n|---|---|")


def test_ragged_table_is_rejected():
    with pytest.raises(ValueError, match="one cell per header"):
        blocks("| A | B |\n|---|---|\n| 1 |")


def test_section_nests_subsections_by_heading_level():
    text = "Intro.\n\n### Sub one\nBody one.\n\n#### Deep\nDeep body.\n\n### Sub two\nBody two."
    result = section("Top", text)
    assert result.title == "Top"
    assert result.blocks[0] == m.Paragraph("Intro.")
    sub_one, sub_two = result.blocks[1], result.blocks[2]
    assert sub_one.title == "Sub one"
    assert sub_one.blocks[1].title == "Deep"
    assert sub_two.blocks == (m.Paragraph("Body two."),)


def test_section_without_subheadings_is_flat():
    result = section("Flat", "Just text.\n\n- a\n- b")
    assert [type(b).__name__ for b in result.blocks] == ["Paragraph", "BulletList"]


def test_section_accepts_indented_text_as_written_inside_python_strings():
    text = """
        Intro paragraph.

        ### Indented heading
        Body under it.
    """
    result = section("Top", text)
    assert result.blocks[1].title == "Indented heading"
    assert result.blocks[1].blocks == (m.Paragraph("Body under it."),)


def test_long_table_rows_may_wrap_onto_the_next_line():
    text = "| A | B |\n|---|---|\n| one | a long cell that\nwraps here |\n| two | short |"
    table = blocks(text)[0]
    assert table.rows == (("one", "a long cell that wraps here"), ("two", "short"))

import dataclasses

import pytest

from app.datagen.model import (
    BulletList,
    Document,
    Note,
    NumberedList,
    Paragraph,
    Section,
    Table,
    count_blocks,
    full_text,
    headings,
    text_units,
    walk_document,
    word_count,
)


def sample() -> Document:
    return Document(
        title="Sample Policy",
        subtitle="For testing",
        metadata=(("Document number", "TST-001"), ("Version", "1")),
        sections=(
            Section(
                "Purpose",
                (Paragraph("This is the purpose."), Note("Keep this short.", "Tip")),
            ),
            Section(
                "Rules",
                (
                    BulletList(("first rule", "second rule")),
                    Section(
                        "Details",
                        (
                            NumberedList(("step one", "step two")),
                            Table(("Name", "Value"), (("a", "1"), ("b", "2")), caption="Values"),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_blocks_are_immutable():
    paragraph = Paragraph("hello")
    with pytest.raises(dataclasses.FrozenInstanceError):
        paragraph.text = "changed"


@pytest.mark.parametrize(
    "build",
    [
        lambda: Paragraph(""),
        lambda: Paragraph("   "),
        lambda: BulletList(()),
        lambda: BulletList(("",)),
        lambda: NumberedList(("a", " ")),
        lambda: Note(""),
        lambda: Section("", (Paragraph("x"),)),
        lambda: Section("Title", ()),
        lambda: Document("", "sub", (), (Section("S", (Paragraph("x"),)),)),
        lambda: Document("Title", "sub", (), ()),
    ],
    ids=[
        "empty-paragraph",
        "blank-paragraph",
        "empty-bullets",
        "empty-bullet-item",
        "blank-numbered-item",
        "empty-note",
        "empty-section-title",
        "section-without-blocks",
        "empty-document-title",
        "document-without-sections",
    ],
)
def test_invalid_blocks_are_rejected(build):
    with pytest.raises(ValueError):
        build()


def test_lists_must_be_tuples():
    with pytest.raises(ValueError):
        BulletList(["a", "b"])


def test_ragged_or_empty_tables_are_rejected():
    with pytest.raises(ValueError):
        Table(("a", "b"), (("1",),))
    with pytest.raises(ValueError):
        Table(("a",), ())


def test_unknown_block_types_are_rejected():
    with pytest.raises(ValueError):
        Section("Title", ("just a string",))


def test_walk_visits_every_block_with_its_depth():
    visited = [(depth, type(block).__name__) for depth, block in walk_document(sample())]
    assert visited == [
        (0, "Section"),
        (1, "Paragraph"),
        (1, "Note"),
        (0, "Section"),
        (1, "BulletList"),
        (1, "Section"),
        (2, "NumberedList"),
        (2, "Table"),
    ]


def test_headings_have_levels():
    assert headings(sample()) == [(1, "Purpose"), (1, "Rules"), (2, "Details")]


def test_text_units_are_paragraphs_notes_and_list_items_only():
    assert text_units(sample()) == [
        "This is the purpose.",
        "Keep this short.",
        "first rule",
        "second rule",
        "step one",
        "step two",
    ]


def test_full_text_includes_titles_tables_and_metadata():
    text = full_text(sample())
    for expected in (
        "Sample Policy",
        "For testing",
        "TST-001",
        "Tip",
        "Values",
        "Name",
        "second rule",
    ):
        assert expected in text


def test_counts():
    document = sample()
    assert count_blocks(document, Table) == 1
    assert count_blocks(document, Section) == 3
    assert word_count(document) == len(full_text(document).split())
    assert word_count(document) > 0

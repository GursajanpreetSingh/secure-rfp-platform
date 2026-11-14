"""A small, deterministic sample document used by tests and smoke checks."""

from app.datagen import model as m

_FILLER = (
    "This sample paragraph exists only to exercise the writers and the page counter; "
    "it carries no company facts and is never used in the real corpus."
)


def sample_document(sections: int = 3, paragraphs_per_section: int = 3) -> m.Document:
    """Build a document whose text is unique per paragraph, so repetition checks stay quiet."""
    built = []
    for i in range(1, sections + 1):
        blocks: list = []
        for j in range(1, paragraphs_per_section + 1):
            blocks.append(m.Paragraph(f"Section {i}, paragraph {j}. " + _FILLER * 4))
        blocks.append(m.BulletList((f"Point {i}.1 of the sample.", f"Point {i}.2 of the sample.")))
        blocks.append(
            m.Table(
                ("Item", "Value"),
                ((f"Row {i}.1", "alpha"), (f"Row {i}.2", "beta")),
                f"Sample table {i}",
            )
        )
        built.append(m.Section(f"Sample section {i}", tuple(blocks)))
    return m.Document(
        "Sample Document", "Generator smoke test", (("Version", "1.0"),), tuple(built)
    )

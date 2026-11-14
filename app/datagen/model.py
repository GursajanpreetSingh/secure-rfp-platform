import re
from collections.abc import Iterator
from dataclasses import dataclass


def _need_text(value, what: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} must be non-empty text")


def _need_items(items, what: str) -> None:
    if not isinstance(items, tuple) or not items:
        raise ValueError(f"{what} must be a non-empty tuple")
    for item in items:
        _need_text(item, f"each item in {what}")


@dataclass(frozen=True)
class Paragraph:
    text: str

    def __post_init__(self) -> None:
        _need_text(self.text, "paragraph text")


@dataclass(frozen=True)
class Note:
    """A highlighted remark, such as a warning or a tip."""

    text: str
    label: str = "Note"

    def __post_init__(self) -> None:
        _need_text(self.text, "note text")
        _need_text(self.label, "note label")


@dataclass(frozen=True)
class BulletList:
    items: tuple[str, ...]

    def __post_init__(self) -> None:
        _need_items(self.items, "a bullet list")


@dataclass(frozen=True)
class NumberedList:
    items: tuple[str, ...]

    def __post_init__(self) -> None:
        _need_items(self.items, "a numbered list")


@dataclass(frozen=True)
class Table:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    caption: str | None = None

    def __post_init__(self) -> None:
        _need_items(self.headers, "table headers")
        if not isinstance(self.rows, tuple) or not self.rows:
            raise ValueError("a table needs at least one row")
        for row in self.rows:
            if not isinstance(row, tuple) or len(row) != len(self.headers):
                raise ValueError("every table row must be a tuple with one cell per header")
            if not all(isinstance(cell, str) for cell in row):
                raise ValueError("table cells must be text")
        if self.caption is not None:
            _need_text(self.caption, "table caption")


@dataclass(frozen=True)
class PageBreak:
    """Start the next block on a new page."""


@dataclass(frozen=True)
class Section:
    """A titled group of blocks. Sections may contain sections, which become sub-headings."""

    title: str
    blocks: tuple["Block", ...]

    def __post_init__(self) -> None:
        _need_text(self.title, "section title")
        if not isinstance(self.blocks, tuple) or not self.blocks:
            raise ValueError("a section needs at least one block")
        for block in self.blocks:
            if not isinstance(block, BLOCK_TYPES):
                raise ValueError(f"unsupported block type: {type(block).__name__}")


BLOCK_TYPES = (Paragraph, Note, BulletList, NumberedList, Table, PageBreak, Section)
Block = Paragraph | Note | BulletList | NumberedList | Table | PageBreak | Section


@dataclass(frozen=True)
class Document:
    title: str
    subtitle: str
    metadata: tuple[tuple[str, str], ...]  # (label, value) pairs for the cover and control table
    sections: tuple[Section, ...]

    def __post_init__(self) -> None:
        _need_text(self.title, "document title")
        if not isinstance(self.subtitle, str):
            raise ValueError("document subtitle must be text")
        if not isinstance(self.metadata, tuple):
            raise ValueError("document metadata must be a tuple of (label, value) pairs")
        for pair in self.metadata:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("metadata entries must be (label, value) pairs")
            _need_text(pair[0], "metadata label")
            _need_text(pair[1], "metadata value")
        if (
            not isinstance(self.sections, tuple)
            or not self.sections
            or not all(isinstance(s, Section) for s in self.sections)
        ):
            raise ValueError("a document needs at least one top-level section")


def walk(blocks: tuple[Block, ...], depth: int = 0) -> Iterator[tuple[int, Block]]:
    """Visit every block in reading order, with how deeply it is nested."""
    for block in blocks:
        yield depth, block
        if isinstance(block, Section):
            yield from walk(block.blocks, depth + 1)


def walk_document(document: Document) -> Iterator[tuple[int, Block]]:
    return walk(document.sections)


def headings(document: Document) -> list[tuple[int, str]]:
    """(level, title) for every section. Top-level sections are level 1."""
    return [
        (depth + 1, block.title)
        for depth, block in walk_document(document)
        if isinstance(block, Section)
    ]


def text_units(document: Document) -> list[str]:
    """Paragraphs, notes and list items. Used to look for repeated text."""
    units: list[str] = []
    for _, block in walk_document(document):
        if isinstance(block, (Paragraph, Note)):
            units.append(block.text)
        elif isinstance(block, (BulletList, NumberedList)):
            units.extend(block.items)
    return units


def full_text(document: Document) -> str:
    """Every piece of text in the document, including titles, tables and metadata."""
    parts = [document.title, document.subtitle]
    for label, value in document.metadata:
        parts.extend([label, value])
    for _, block in walk_document(document):
        if isinstance(block, Section):
            parts.append(block.title)
        elif isinstance(block, Paragraph):
            parts.append(block.text)
        elif isinstance(block, Note):
            parts.extend([block.label, block.text])
        elif isinstance(block, (BulletList, NumberedList)):
            parts.extend(block.items)
        elif isinstance(block, Table):
            if block.caption:
                parts.append(block.caption)
            parts.extend(block.headers)
            for row in block.rows:
                parts.extend(row)
    return "\n".join(parts)


def word_count(document: Document) -> int:
    return len(re.findall(r"\S+", full_text(document)))


def count_blocks(document: Document, kind: type) -> int:
    return sum(1 for _, block in walk_document(document) if isinstance(block, kind))

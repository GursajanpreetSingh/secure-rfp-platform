"""A tiny text markup that turns authored prose into model blocks.

Authors write text like this (a blank line between blocks)::

    A normal paragraph, wrapped across lines however you like.

    - bullet one (a long bullet may wrap onto
      the next line)
    - bullet two

    1. numbered one
    2. numbered two

    NOTE: a highlighted note.      (also IMPORTANT: and WARNING:)

    | Header A | Header B |
    |---|---|
    | cell | cell |
    Caption: an optional table caption

    ### A sub-section heading       (#### and ##### nest deeper)
"""

import re

from app.datagen import model as m

_NOTE = re.compile(r"^(NOTE|IMPORTANT|WARNING):\s*", re.IGNORECASE)
_NUMBERED = re.compile(r"^\d+\.\s+")
_SEPARATOR = re.compile(r"^\|?[\s:|-]+\|?$")


def _join(lines: list[str]) -> str:
    return " ".join(lines)


def _items(lines: list[str], is_marker) -> list[str]:
    """Group wrapped lines under the bullet or number that started them."""
    items: list[list[str]] = []
    for line in lines:
        if is_marker(line) or not items:
            items.append([line])
        else:
            items[-1].append(line)
    return [_join(item) for item in items]


def _is_bullet(line: str) -> bool:
    return line.startswith("- ")


def _is_numbered(line: str) -> bool:
    return bool(_NUMBERED.match(line))


def _table(lines: list[str]) -> m.Table:
    caption = None
    if lines[-1].startswith("Caption:"):
        caption = lines.pop()[len("Caption:") :].strip()
    rows: list[str] = []
    for line in lines:
        if line.startswith("|") or not rows:
            rows.append(line)
        else:  # a long row wrapped onto the next line
            rows[-1] += " " + line
    rows = [row for row in rows if not _SEPARATOR.match(row)]
    cells = [tuple(c.strip() for c in row.strip("|").split("|")) for row in rows]
    if len(cells) < 2:
        raise ValueError(f"a table needs a header row and at least one data row: {lines!r}")
    return m.Table(cells[0], tuple(cells[1:]), caption)


def _block(lines: list[str]) -> m.Block:
    first = lines[0]
    if first.startswith("|"):
        return _table(lines)
    if _is_bullet(first):
        return m.BulletList(tuple(line[2:].strip() for line in _items(lines, _is_bullet)))
    if _is_numbered(first):
        items = _items(lines, _is_numbered)
        return m.NumberedList(tuple(_NUMBERED.sub("", item).strip() for item in items))
    note = _NOTE.match(first)
    if note:
        return m.Note(
            _join([_NOTE.sub("", first, count=1), *lines[1:]]), note.group(1).capitalize()
        )
    return m.Paragraph(_join(lines))


def blocks(text: str) -> tuple[m.Block, ...]:
    """Parse markup that has no headings into blocks."""
    result = []
    for chunk in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if lines:
            result.append(_block(lines))
    return tuple(result)


def section(title: str, text: str, level: int = 1) -> m.Section:
    """Parse markup with ``###`` sub-headings into a (nested) Section."""
    marker = "#" * (level + 2)
    parts = re.split(rf"(?m)^[ \t]*{marker} (.+)$", text.strip("\n"))
    content = list(blocks(parts[0]))
    for sub_title, sub_text in zip(parts[1::2], parts[2::2], strict=True):
        content.append(section(sub_title.strip(), sub_text, level + 1))
    return m.Section(title, tuple(content))

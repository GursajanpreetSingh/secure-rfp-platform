"""Split an extracted document into section chunks and passage chunks.

A section chunk holds one section (heading plus its text) and gives context.
A passage chunk is a small piece of one section and is what search will match.
Every passage points at its section through `parent_key`.
Permissions are copied onto chunks in a later step, not here.
"""

import math
import re
from dataclasses import dataclass

from app.ingestion.extract import ExtractedDocument

PASSAGE_WORDS = 220  # target maximum words of body text in a passage
TAIL_MERGE_WORDS = 40  # a shorter last piece is merged into the one before it
OVERLAP_WORDS = 30  # the last line of a passage is repeated in the next if it is this short
WORDS_TO_TOKENS = 1.3  # rough estimate, good enough for sizing
SKIPPED_SECTIONS = {"contents", "table of contents"}

HEADING = re.compile(r"^(#{1,6}) (.+)$")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
FRONT_MATTER = "Front matter"


@dataclass(frozen=True)
class ChunkDraft:
    key: str  # "s4" for a section, "s4-p2" for a passage
    parent_key: str | None
    level: str  # "section" or "passage"
    chunk_index: int  # position among chunks of the same level, in document order
    content: str
    page: int | None
    section: str  # heading path, for example "5. Workload model > Think times"
    token_count: int
    from_ocr: bool


@dataclass(frozen=True)
class _Line:
    page: int | None
    text: str
    from_ocr: bool


@dataclass
class _Section:
    path: str
    page: int | None
    lines: list[_Line]


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text.split()) * WORDS_TO_TOKENS)


def _sections(document: ExtractedDocument) -> list[_Section]:
    sections = [_Section(FRONT_MATTER, None, [])]
    stack: list[tuple[int, str]] = []
    for page in document.pages:
        for raw in page.text.splitlines():
            text = raw.strip()
            if not text:
                continue
            match = HEADING.match(text)
            if match:
                level, title = len(match.group(1)), match.group(2).strip()
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))
                path = " > ".join(name for _, name in stack)
                sections.append(_Section(path, page.number, []))
            else:
                if not sections[-1].lines and sections[-1].page is None:
                    sections[-1].page = page.number
                sections[-1].lines.append(_Line(page.number, text, page.from_ocr))
    return [
        section
        for section in sections
        if section.lines and section.path.split(" > ")[-1].lower() not in SKIPPED_SECTIONS
    ]


def _units(lines: list[_Line]) -> list[_Line]:
    """Lines, with any very long line split at sentence ends."""
    units = []
    for line in lines:
        if len(line.text.split()) <= PASSAGE_WORDS:
            units.append(line)
            continue
        for sentence in SENTENCE_END.split(line.text):
            units.append(_Line(line.page, sentence, line.from_ocr))
    return units


def _words(units: list[_Line]) -> int:
    return sum(len(unit.text.split()) for unit in units)


def _pack(units: list[_Line]) -> list[list[_Line]]:
    """Group lines into passages. A short last line is repeated at the start of the next."""
    groups: list[list[_Line]] = []
    overlaps: list[int] = []
    current: list[_Line] = []
    carried = 0
    for unit in units:
        if current and _words(current) + len(unit.text.split()) > PASSAGE_WORDS:
            groups.append(current)
            overlaps.append(carried)
            last = current[-1]
            keep = len(last.text.split()) <= OVERLAP_WORDS
            current = [last] if keep else []
            carried = 1 if keep else 0
        current.append(unit)
    if current:
        groups.append(current)
        overlaps.append(carried)
    if len(groups) > 1 and _words(groups[-1][overlaps[-1] :]) < TAIL_MERGE_WORDS:
        tail = groups.pop()
        groups[-1].extend(tail[overlaps.pop() :])
    return groups


def chunk_document(document: ExtractedDocument) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    passage_index = 0
    for section_index, section in enumerate(_sections(document)):
        key = f"s{section_index}"
        body = "\n".join(line.text for line in section.lines)
        full = f"{section.path}\n{body}"
        chunks.append(
            ChunkDraft(
                key=key,
                parent_key=None,
                level="section",
                chunk_index=section_index,
                content=full,
                page=section.page,
                section=section.path[:255],
                token_count=estimate_tokens(full),
                from_ocr=any(line.from_ocr for line in section.lines),
            )
        )
        for number, group in enumerate(_pack(_units(section.lines))):
            text = f"{section.path}\n" + "\n".join(unit.text for unit in group)
            chunks.append(
                ChunkDraft(
                    key=f"{key}-p{number}",
                    parent_key=key,
                    level="passage",
                    chunk_index=passage_index,
                    content=text,
                    page=group[0].page,
                    section=section.path[:255],
                    token_count=estimate_tokens(text),
                    from_ocr=any(unit.from_ocr for unit in group),
                )
            )
            passage_index += 1
    return chunks

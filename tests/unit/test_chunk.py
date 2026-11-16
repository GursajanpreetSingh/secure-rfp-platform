from functools import cache
from pathlib import Path

import pytest

from app.corpus.manifest import load_manifest
from app.ingestion.chunk import PASSAGE_WORDS, ChunkDraft, chunk_document
from app.ingestion.extract import ExtractedDocument, ExtractedPage, extract

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
ENTRIES = {entry.id: entry for entry in load_manifest().documents}
TEXT_DOCS = sorted(set(ENTRIES) - {"DOC-009"})


@cache
def _chunks(doc_id: str) -> list[ChunkDraft]:
    return chunk_document(extract(RAW / ENTRIES[doc_id].filename))


def _page(text: str, number: int | None = 1) -> ExtractedDocument:
    return ExtractedDocument(pages=(ExtractedPage(number, text),))


@pytest.mark.parametrize("doc_id", TEXT_DOCS)
def test_structure_is_consistent(doc_id: str) -> None:
    chunks = _chunks(doc_id)
    sections = {c.key: c for c in chunks if c.level == "section"}
    passages = [c for c in chunks if c.level == "passage"]
    assert len(sections) >= 10 and passages
    for passage in passages:
        assert passage.parent_key in sections
        assert sections[passage.parent_key].section == passage.section
        assert passage.content.startswith(passage.section)
        assert len(passage.content.split()) <= PASSAGE_WORDS + 60
        assert not passage.from_ocr
    for level in ("section", "passage"):
        indexes = [c.chunk_index for c in chunks if c.level == level]
        assert indexes == list(range(len(indexes)))
    assert len({c.key for c in chunks}) == len(chunks)


@pytest.mark.parametrize("doc_id", TEXT_DOCS)
def test_contents_list_is_not_chunked(doc_id: str) -> None:
    assert not any(c.section.lower().endswith("contents") for c in _chunks(doc_id))


@pytest.mark.parametrize("doc_id", ["DOC-001", "DOC-004", "DOC-007", "DOC-014"])
def test_no_body_line_is_lost(doc_id: str) -> None:
    document = extract(RAW / ENTRIES[doc_id].filename)
    passages = "\n".join(c.content for c in _chunks(doc_id) if c.level == "passage")
    in_contents = False
    for line in document.text.splitlines():
        if line.startswith("#"):
            in_contents = line.lower() == "# contents"
            continue
        if in_contents or len(line.split()) > 100:
            continue
        assert line in passages


def test_key_facts_land_in_a_passage_with_page_and_section() -> None:
    hits = [c for c in _chunks("DOC-004") if c.level == "passage" and "300 ms" in c.content]
    assert hits
    assert all(c.page is not None and c.section for c in hits)


def test_docx_and_txt_chunks_have_no_page() -> None:
    assert all(c.page is None for c in _chunks("DOC-006"))
    assert all(c.page is None for c in _chunks("DOC-014"))


def test_pdf_chunks_have_pages() -> None:
    assert all(c.page and c.page >= 1 for c in _chunks("DOC-001"))


def test_nested_headings_become_a_path() -> None:
    doc = _page("# 5. Workload\nintro text here\n## Think times\nusers pause 5 seconds")
    sections = [c.section for c in chunk_document(doc) if c.level == "section"]
    assert sections == ["5. Workload", "5. Workload > Think times"]


def test_sibling_heading_replaces_the_previous_one() -> None:
    doc = _page("# A\na text\n## A1\na1 text\n## A2\na2 text\n# B\nb text")
    sections = [c.section for c in chunk_document(doc) if c.level == "section"]
    assert sections == ["A", "A > A1", "A > A2", "B"]


def test_heading_without_text_makes_no_chunk() -> None:
    doc = _page("# Empty\n## Child\nchild text")
    sections = [c.section for c in chunk_document(doc) if c.level == "section"]
    assert sections == ["Empty > Child"]


def test_text_before_first_heading_is_front_matter() -> None:
    doc = _page("loose text\n# One\nbody")
    first = chunk_document(doc)[0]
    assert first.section == "Front matter"


def test_long_section_splits_into_overlapping_passages() -> None:
    lines = [f"line {i} " + "word " * 19 for i in range(30)]  # 21 words each
    doc = _page("# Long\n" + "\n".join(lines))
    passages = [c for c in chunk_document(doc) if c.level == "passage"]
    assert len(passages) >= 3
    first_last = passages[0].content.splitlines()[-1]
    assert first_last in passages[1].content  # short last line is repeated
    for passage in passages:
        assert len(passage.content.split()) <= PASSAGE_WORDS + 10


def test_very_long_line_is_split_at_sentences() -> None:
    sentence = "This is one sentence with some words in it for the test. "
    doc = _page("# Big\n" + sentence * 60)
    passages = [c for c in chunk_document(doc) if c.level == "passage"]
    assert len(passages) >= 2
    assert all(len(c.content.split()) <= PASSAGE_WORDS + 20 for c in passages)


def test_tiny_last_piece_is_merged_into_the_previous_passage() -> None:
    lines = ["a " * 100 + "end"] * 2 + ["tail words only"]
    doc = _page("# T\n" + "\n".join(lines))
    passages = [c for c in chunk_document(doc) if c.level == "passage"]
    assert "tail words only" in passages[-1].content
    assert sum("tail words only" in c.content for c in passages) == 1


def test_token_count_is_filled() -> None:
    chunks = chunk_document(_page("# H\n" + "word " * 100))
    assert all(c.token_count > 100 for c in chunks)

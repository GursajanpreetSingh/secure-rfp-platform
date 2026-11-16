import pytest

from app.retrieval.search import RRF_K, build_tsquery, fuse_rankings


def test_tsquery_matches_any_word_and_quotes_each() -> None:
    assert build_tsquery("encryption at rest") == "'encryption' | 'at' | 'rest'"


def test_tsquery_keeps_compound_terms_and_numbers() -> None:
    query = build_tsquery("AES-256 and 99.9% uptime")
    assert "'aes-256'" in query
    assert "'99.9'" in query
    assert "'uptime'" in query


def test_tsquery_drops_duplicates_and_one_letter_words() -> None:
    assert build_tsquery("Backup backup a BACKUP") == "'backup'"


def test_tsquery_cannot_be_broken_by_punctuation() -> None:
    query = build_tsquery("x'); DROP TABLE chunks; -- & | ! ( ) :*")
    assert query is not None
    assert "'drop'" in query
    for character in "&!()*:;":
        assert character not in query.replace(" | ", "")


@pytest.mark.parametrize("question", ["", "   ", "?!.,", "& | !"])
def test_tsquery_of_nothing_is_none(question: str) -> None:
    assert build_tsquery(question) is None


def test_tsquery_is_limited_in_length() -> None:
    query = build_tsquery(" ".join(f"word{i}" for i in range(200)))
    assert query.count("|") + 1 == 24


def test_fusion_rewards_chunks_found_by_both_searches() -> None:
    fused = dict(fuse_rankings(["a", "b", "c"], ["c", "d"]))
    assert fused["c"] == pytest.approx(1 / (RRF_K + 3) + 1 / (RRF_K + 1))
    assert fused["c"] > fused["a"] > fused["b"]
    assert set(fused) == {"a", "b", "c", "d"}


def test_fusion_order_is_best_first_and_stable() -> None:
    ranked = [chunk for chunk, _ in fuse_rankings(["x", "y"], ["y", "x"])]
    assert ranked == ["x", "y"]  # equal scores are broken by id, so results never flip
    assert fuse_rankings([], []) == []


def test_fusion_with_one_empty_list_keeps_the_other_order() -> None:
    assert [c for c, _ in fuse_rankings([], ["p", "q", "r"])] == ["p", "q", "r"]

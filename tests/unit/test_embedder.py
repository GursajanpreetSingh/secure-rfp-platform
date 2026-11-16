import os

import numpy as np
import pytest

from app.models.chunk import EMBEDDING_DIM
from app.retrieval.embedder import QUERY_PREFIX, LocalEmbedder


class _WrongSizeModel:
    def embed(self, texts):
        return (np.zeros(7) for _ in texts)


def test_wrong_size_vectors_are_rejected() -> None:
    embedder = LocalEmbedder()
    embedder._model = _WrongSizeModel()
    with pytest.raises(ValueError, match="expects"):
        embedder.embed_passages(["text"])


def test_no_texts_means_no_model_load() -> None:
    assert LocalEmbedder().embed_passages([]) == []


def test_queries_get_the_search_prefix() -> None:
    seen = []

    class Spy:
        def embed(self, texts):
            seen.extend(texts)
            return (np.zeros(EMBEDDING_DIM) for _ in texts)

    embedder = LocalEmbedder()
    embedder._model = Spy()
    embedder.embed_query("do you encrypt data?")
    embedder.embed_passages(["a passage"])
    assert seen == [QUERY_PREFIX + "do you encrypt data?", "a passage"]


@pytest.mark.skipif(
    os.environ.get("RUN_MODEL_TESTS") != "1", reason="set RUN_MODEL_TESTS=1 to load the model"
)
def test_real_model_understands_similar_meaning() -> None:
    embedder = LocalEmbedder()
    a, b, c = embedder.embed_passages(
        [
            "We encrypt data at rest with AES-256",
            "Stored information is protected using strong encryption",
            "Our office is closed on Sundays",
        ]
    )
    assert len(a) == EMBEDDING_DIM
    assert float(np.dot(a, b)) > float(np.dot(a, c)) + 0.1

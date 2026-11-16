"""Turn text into vectors with a local model. Nothing leaves the machine."""

from functools import lru_cache
from typing import Protocol

from app.models.chunk import EMBEDDING_DIM

MODEL_NAME = "BAAI/bge-small-en-v1.5"
# BGE models search better when the question (not the passages) starts with this sentence.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class LocalEmbedder:
    """Runs the model on the CPU through fastembed. The model loads on first use."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding  # imported here so tests need not load it

            self._model = TextEmbedding(self._model_name)
        return self._model

    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors = [vector.tolist() for vector in self._load().embed(texts)]
        for vector in vectors:
            if len(vector) != EMBEDDING_DIM:
                raise ValueError(
                    f"model gives {len(vector)} numbers per text but the database expects "
                    f"{EMBEDDING_DIM}"
                )
        return vectors

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts) if texts else []

    def embed_query(self, text: str) -> list[float]:
        return self._embed([QUERY_PREFIX + text])[0]


@lru_cache
def get_embedder() -> LocalEmbedder:
    return LocalEmbedder()

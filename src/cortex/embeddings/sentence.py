from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING

from cortex.embeddings.provider import EmbeddingProvider

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_MODELS: dict[str, SentenceTransformer] = {}
_MODELS_LOCK = Lock()


class SentenceTransformersEmbeddings(EmbeddingProvider):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._model().encode(texts, normalize_embeddings=True).tolist()

    def _model(self) -> SentenceTransformer:
        from sentence_transformers import SentenceTransformer

        with _MODELS_LOCK:
            model = _MODELS.get(self._model_name)
            if model is None:
                model = SentenceTransformer(self._model_name)
                _MODELS[self._model_name] = model
            return model
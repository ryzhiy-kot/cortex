import httpx

from cortex.embeddings.provider import EmbeddingProvider


class OllamaEmbeddings(EmbeddingProvider):
    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.Client(base_url=self._base_url, timeout=60)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            response = self._client.post(
                "/api/embeddings",
                json={"model": self._model, "prompt": text},
            )
            response.raise_for_status()
            vectors.append(response.json()["embedding"])
        return vectors
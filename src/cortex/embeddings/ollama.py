from ollama import Client

from cortex.embeddings.provider import EmbeddingProvider


class OllamaEmbeddings(EmbeddingProvider):
    def __init__(self, base_url: str, model: str) -> None:
        self._client = Client(host=base_url.rstrip("/"), timeout=60)
        self._model = model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embed(model=self._model, input=texts)
        return [list(item) for item in response.embeddings]
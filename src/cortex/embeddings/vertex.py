


from cortex.embeddings.provider import EmbeddingProvider


class VertexEmbeddings(EmbeddingProvider):
    def __init__(self, project: str, location: str, model: str = "text-embedding-005") -> None:
        import vertexai
        from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

        self._model = TextEmbeddingModel.from_pretrained(model)
        self._textify = TextEmbeddingInput
        vertexai.init(project=project, location=location)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        inputs = [self._textify(text) for text in texts]
        embeddings = self._model.get_embeddings(inputs)
        return [embedding.values for embedding in embeddings]
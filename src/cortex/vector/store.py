import chromadb

from cortex.embeddings.provider import EmbeddingProvider


class VectorStore:
    def __init__(self, path: str, collection: str, embeddings: EmbeddingProvider) -> None:
        self._client = chromadb.PersistentClient(path=path)
        self._collection = self._client.get_or_create_collection(
            name=collection,
            embedding_function=None,
        )
        self._embeddings = embeddings

    def upsert_concept(self, concept_path: str, text: str, metadata: dict) -> None:
        embedding = self._embeddings.embed_texts([text])[0]
        self._collection.upsert(
            ids=[concept_path],
            embeddings=[embedding],
            metadatas=[metadata],
            documents=[text],
        )

    def delete(self, concept_paths: list[str]) -> None:
        if concept_paths:
            self._collection.delete(ids=concept_paths)

    def concept_paths(self) -> set[str]:
        return set(self._collection.get(include=[])["ids"])

    def query_vector(self, query: str, top_k: int, where: dict | None = None) -> list[dict]:
        query_embedding = self._embeddings.embed_texts([query])[0]
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return self._pack(results)

    def query_lexical(self, query: str, top_k: int, where: dict | None = None) -> list[dict]:
        results = self._collection.get(
            where=where,
            where_document={"$contains": query},
            include=["documents", "metadatas"],
        )
        ids = results["ids"]
        documents = results["documents"]
        metadatas = results["metadatas"]
        packed = []
        for i, concept_path in enumerate(ids):
            packed.append(
                {
                    "concept_path": concept_path,
                    "body": documents[i],
                    "metadata": metadatas[i],
                    "distance": 0.0,
                }
            )
        return packed[:top_k]

    def _pack(self, results: dict) -> list[dict]:
        packed = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for i, concept_path in enumerate(ids):
            packed.append(
                {
                    "concept_path": concept_path,
                    "body": documents[i],
                    "metadata": metadatas[i],
                    "distance": distances[i],
                }
            )
        return packed
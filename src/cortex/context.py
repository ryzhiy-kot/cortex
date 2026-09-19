from cortex.bundle.gcs import GCSBundleStore
from cortex.bundle.local import LocalBundleStore
from cortex.bundle.parser import parse_concept
from cortex.embeddings.ollama import OllamaEmbeddings
from cortex.embeddings.provider import EmbeddingProvider
from cortex.embeddings.sentence import SentenceTransformersEmbeddings
from cortex.embeddings.vertex import VertexEmbeddings
from cortex.ingest import Ingester
from cortex.models import ConceptCard, ConceptResponse, ListingResponse
from cortex.settings import BundleStoreKind, EmbeddingProviderKind, Settings
from cortex.vector.store import VectorStore


class Cortex:
    def __init__(self, settings: Settings, embeddings: EmbeddingProvider | None = None) -> None:
        self._settings = settings
        self.store = _build_store(settings)
        self.embeddings = embeddings or _build_embeddings(settings)
        self.vector = VectorStore(
            path=str(settings.chroma_path),
            collection=settings.chroma_collection,
            embeddings=self.embeddings,
        )
        self.ingester = Ingester(self.store, self.vector, self.embeddings)

    def ingest(self, path: str | None = None) -> dict:
        response = self.ingester.ingest(path or "")
        return response.model_dump()

    def search(self, request) -> dict:
        from cortex.search import search

        results = search(request, self.vector)
        return [result.model_dump() for result in results]

    def read_concept(self, concept_path: str) -> ConceptResponse:
        concept_path = concept_path.strip("/")
        rel_path = f"{concept_path}.md"
        raw = self.store.read_text(rel_path)
        parsed = parse_concept(raw, rel_path)
        return ConceptResponse(
            concept_path=parsed.path,
            frontmatter=parsed.frontmatter,
            body=parsed.body,
            links=parsed.links,
        )

    def list_dir(self, rel_dir: str) -> ListingResponse:
        rel_dir = rel_dir.strip("/")
        concepts = self.store.list_markdown(rel_dir)
        subdirs = self.store.list_subdirs(rel_dir)
        if self.store.exists(f"{rel_dir}/index.md" if rel_dir else "index.md"):
            index_content = self.store.read_text(f"{rel_dir}/index.md" if rel_dir else "index.md")
        else:
            index_content = None
        return ListingResponse(
            dir=rel_dir,
            subdirs=subdirs,
            concepts=[self._card(rel_dir, name) for name in concepts],
            index_content=index_content,
        )

    def _card(self, rel_dir: str, name: str) -> ConceptCard:
        if not name.endswith(".md"):
            name = f"{name}.md"
        rel_path = f"{rel_dir}/{name}" if rel_dir else name
        path = rel_path[: -len(".md")]
        try:
            parsed = parse_concept(self.store.read_text(rel_path), path)
            return ConceptCard(
                concept_path=path,
                type=parsed.frontmatter.get("type", ""),
                title=parsed.frontmatter.get("title"),
                description=parsed.frontmatter.get("description"),
            )
        except Exception:
            return ConceptCard(concept_path=path, type="")


def _build_store(settings: Settings):
    if settings.bundle_store == BundleStoreKind.GCS:
        if not settings.gcs_bucket:
            raise ValueError("CORTEX_GCS_BUCKET is required when bundle_store=gcs")
        return GCSBundleStore(settings.gcs_bucket, settings.gcs_prefix)
    return LocalBundleStore(settings.bundle_root)


def _build_embeddings(settings: Settings) -> EmbeddingProvider:
    match settings.embedding_provider:
        case EmbeddingProviderKind.OLLAMA:
            return OllamaEmbeddings(settings.ollama_base_url, settings.ollama_embedding_model)
        case EmbeddingProviderKind.VERTEX:
            if not settings.vertex_project:
                raise ValueError("CORTEX_VERTEX_PROJECT is required when embedding_provider=vertex")
            return VertexEmbeddings(settings.vertex_project, settings.vertex_location, settings.vertex_embedding_model)
        case EmbeddingProviderKind.SENTENCE_TRANSFORMERS:
            return SentenceTransformersEmbeddings()